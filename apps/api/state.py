"""应用全局状态：存储、超级视频大师、WebSocket 客户端、A2UI 确认管理器。"""

from datetime import datetime, timezone

from core.a2ui.manager import ConfirmationManager
from core.agents.conversation import ConversationStore
from core.interaction_log.file_store import InteractionFileStore
from core.interaction_log.recorder import InteractionRecorder
from core.interaction_log.store import InteractionLogStore
from core.llm.settings import LLMConfigManager
from core.agents.config_manager import AgentConfigManager
from core.super_video_master.super_video_master import SuperVideoMaster
from core.events.emitter import EventEmitter
from core.logging.setup import setup_logging
from core.models.entities import Project, Script
from core.store.memory import MemoryStore
from core.store.persist import load_store, save_store, schedule_save
import shutil
from pathlib import Path


class AppState:
    """FastAPI 应用单例状态容器。"""

    def __init__(self) -> None:
        setup_logging()
        self.store = MemoryStore()
        load_store(self.store)
        self.conversations = ConversationStore()
        self.llm_config = LLMConfigManager()
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
        self.confirmation_manager = ConfirmationManager(self.emitter)
        self.super_video_master = SuperVideoMaster(
            self.store,
            self.emitter,
            self.confirmation_manager,
            self.conversations,
            self.llm_config,
            self.interaction_recorder,
            self.agent_config,
        )
        self.ws_clients: dict[str, list] = {}

    def persist_store(self) -> None:
        schedule_save(self.store)

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
        "project_completed",
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
    """清理历史数据文件与日志（新建项目时调用）。"""
    # 清空 dev_store.json
    store_path = Path("data/dev_store.json")
    if store_path.exists():
        store_path.unlink()
    # 清空 interaction logs
    log_dir = Path("data/logs/interactions")
    if log_dir.exists():
        shutil.rmtree(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
    # 重置内存 store（就地清空，保持 super_video_master 等组件引用一致）
    state.store.clear()
    load_store(state.store)


def create_project(title: str | None = None) -> Project:
    # 新建项目前清理历史
    reset_history()
    if not title or not title.strip():
        now = datetime.now(timezone.utc)
        short = now.strftime("%m%d%H%M")
        title = f"视频项目-{short}"
    project = Project(title=title, created_at=datetime.now(timezone.utc).isoformat())
    state.store.add_project(project)
    state.persist_store()
    return project


def create_script(project_id: str, title: str, duration_sec: int = 60) -> Script:
    script = Script(project_id=project_id, title=title, duration_sec=duration_sec)
    state.store.add_script(script)
    state.persist_store()
    return script
