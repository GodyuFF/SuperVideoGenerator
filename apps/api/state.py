"""应用全局状态：存储、超级视频大师、WebSocket 客户端、A2UI 确认管理器。"""

from datetime import datetime, timezone

from core.llm.a2ui.manager import ConfirmationManager
from core.conversation import ConversationIndex, ConversationStore
from core.conversation.sqlite_store import ConversationSqliteStore
from core.interaction_log.file_store import InteractionFileStore
from core.interaction_log.recorder import InteractionRecorder
from core.interaction_log.store import InteractionLogStore
from core.llm.ai_config import AiConfigManager
from core.llm.client.settings import LLMConfigManager
from core.llm.agent.config_manager import AgentConfigManager
from core.super_video_master.super_video_master import SuperVideoMaster
from core.events.emitter import EventEmitter
from core.logging.setup import setup_logging
from core.models.entities import Project, Script
from core.store.memory import MemoryStore
from core.store.persist import load_store, save_store, schedule_save


class AppState:
    """FastAPI 应用单例状态容器。"""

    def __init__(self) -> None:
        setup_logging()
        self.store = MemoryStore()
        self.conversation_index = ConversationIndex()
        self.conversation_sqlite = ConversationSqliteStore()
        self.conversations = ConversationStore(sqlite_store=self.conversation_sqlite)
        load_store(
            self.store,
            conversation_index=self.conversation_index,
            conversation_store=self.conversations,
        )
        from core.store.persist import configure_persist_hooks

        configure_persist_hooks(conversation_index=self.conversation_index)
        self._sync_conversation_stores()
        self.llm_config = LLMConfigManager()
        self.ai_config = AiConfigManager(self.llm_config)
        self.agent_config = AgentConfigManager()
        self.interaction_log_store = InteractionLogStore()
        self.interaction_file_store = InteractionFileStore()
        self.emitter = EventEmitter()
        self.interaction_recorder = InteractionRecorder(
            self.interaction_log_store,
            self.emitter,
            file_store=self.interaction_file_store,
            emit_ws_events=False,
        )
        self.confirmation_manager = ConfirmationManager(
            self.emitter,
            sqlite_store=self.conversation_sqlite,
        )
        self.super_video_master = SuperVideoMaster(
            self.store,
            self.emitter,
            self.confirmation_manager,
            self.conversations,
            self.llm_config,
            self.interaction_recorder,
            self.agent_config,
            self.conversation_index,
        )
        self.ws_clients: dict[str, list] = {}

    def _sync_conversation_stores(self) -> None:
        """双向同步：SQLite ↔ 内存 index / JSON 消息。"""
        added = self.conversation_index.merge_from_sqlite(self.conversation_sqlite)
        for conv in self.conversation_index.conversations.values():
            self.conversation_sqlite.upsert_conversation(conv)
        if self.conversations.messages:
            self.conversation_sqlite.backfill_messages(self.conversations.messages)
        elif self.conversation_sqlite.message_count() == 0:
            self.conversation_sqlite.import_from_json(
                self.conversation_index.conversations,
                self.conversations.messages,
            )
        if added:
            save_store(
                self.store,
                conversation_index=self.conversation_index,
                conversation_store=None,
            )

    def persist_store(self, *, immediate: bool = False) -> None:
        for conv in self.conversation_index.conversations.values():
            self.conversation_sqlite.upsert_conversation(conv)
        kwargs = {
            "store": self.store,
            "conversation_index": self.conversation_index,
            "conversation_store": None,
        }
        if immediate:
            save_store(**kwargs)
        else:
            schedule_save(**kwargs)

    def channel_key(self, project_id: str, script_id: str) -> str:
        return f"{project_id}:{script_id}"

    async def broadcast(self, project_id: str, script_id: str, event: dict) -> None:
        channel = self.channel_key(project_id, script_id)
        for ws in self.ws_clients.get(channel, []):
            await ws.send_json(event)


state = AppState()


async def _ws_emit_handler(event: dict) -> None:
    script_id = event.get("script_id")
    event_type = event.get("type", "")
    broadcast_types = {
        "master_message",
        "react_thought",
        "react_action",
        "llm_stream_start",
        "llm_stream_delta",
        "llm_stream_end",
        "execution_failed",
        "execution_aborted",
        "execution_abort_requested",
        "execution_paused",
        "execution_resumed",
        "step_awaiting_confirmation",
        "step_resumed",
        "project_completed",
        "react_finished",
        "edit_timeline_updated",
        "export_progress",
    }
    for channel, clients in state.ws_clients.items():
        if script_id and channel.endswith(f":{script_id}"):
            for ws in clients:
                await ws.send_json(event)
        elif event_type.startswith("a2ui_") or event_type in broadcast_types:
            for ws in clients:
                await ws.send_json(event)


state.emitter.subscribe(_ws_emit_handler)


def reset_history() -> None:
    """清理内存存储与 dev_store（新建项目时调用，保留交互日志）。"""
    from core.store.project_paths import DATA_ROOT

    store_path = DATA_ROOT / "dev_store.json"
    if store_path.exists():
        store_path.unlink()
    state.conversation_sqlite.clear_all()
    state.store.clear()
    state.conversation_index.clear()
    state.conversations.clear()
    load_store(state.store)


def create_project(title: str | None = None) -> Project:
    if not title or not title.strip():
        now = datetime.now(timezone.utc)
        short = now.strftime("%m%d%H%M")
        title = f"视频项目-{short}"
    project = Project(title=title, created_at=datetime.now(timezone.utc).isoformat())
    state.store.add_project(project)
    from core.store.project_paths import ensure_project_layout

    ensure_project_layout(project)
    state.persist_store()
    return project


def create_script(project_id: str, title: str, duration_sec: int = 60) -> Script:
    script = Script(project_id=project_id, title=title, duration_sec=duration_sec)
    state.store.add_script(script)
    from core.store.project_paths import ensure_script_layout

    ensure_script_layout(script)
    state.persist_store()
    return script


def delete_script(project_id: str, script_id: str) -> None:
    """删除剧本：MemoryStore、磁盘目录、对话库。"""
    script = state.store.get_script(script_id)
    if script is None or script.project_id != project_id:
        raise ValueError("剧本不存在")
    state.store.delete_script(script_id)
    from core.store.project_paths import remove_script_dir, script_dir

    if not remove_script_dir(project_id, script_id):
        raise ValueError(f"无法删除剧本目录：{script_dir(project_id, script_id)}")
    state.conversation_sqlite.delete_by_script_id(project_id, script_id)
    state.conversation_index.delete_by_script_id(project_id, script_id)
    state.conversations.delete_by_script_id(project_id, script_id)
    state.persist_store(immediate=True)


def delete_project(project_id: str) -> None:
    """删除项目：MemoryStore、data/projects 目录、对话库（保留交互日志）。"""
    from core.store.project_paths import project_dir, remove_project_dir

    in_store = state.store.get_project(project_id) is not None
    on_disk = project_dir(project_id).exists()
    if not in_store and not on_disk:
        raise ValueError("项目不存在")

    if in_store:
        state.store.delete_project(project_id)

    if not remove_project_dir(project_id):
        raise ValueError(f"无法删除项目目录：{project_dir(project_id)}")

    state.conversation_sqlite.delete_by_project_id(project_id)
    state.conversation_index.delete_by_project_id(project_id)
    state.conversations.delete_by_project_id(project_id)
    state.persist_store(immediate=True)


def delete_projects_batch(project_ids: list[str]) -> dict[str, str]:
    """批量删除项目；返回 {project_id: ok|error_message}。"""
    results: dict[str, str] = {}
    for pid in project_ids:
        try:
            delete_project(pid)
            results[pid] = "ok"
        except ValueError as e:
            results[pid] = str(e)
    return results
