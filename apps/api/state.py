"""应用全局状态：存储、超级视频大师、WebSocket 客户端、A2UI 确认管理器。"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from core.llm.a2ui.manager import ConfirmationManager
from core.conversation import ConversationIndex, ConversationStore
from core.conversation.sqlite_store import ConversationSqliteStore
from core.conversation.write_queue import ConversationWriteQueue
from core.interaction_log.file_store import InteractionFileStore
from core.interaction_log.recorder import InteractionRecorder
from core.interaction_log.store import InteractionLogStore
from core.llm.ai_config import AiConfigManager
from core.llm.client.settings import LLMConfigManager
from core.llm.agent.config_manager import AgentConfigManager, get_agent_config_manager
from core.super_video_master.super_video_master import SuperVideoMaster
from core.events.emitter import EventEmitter
from core.logging.perf import PerfSpan, log_perf
from core.logging.setup import setup_logging
from core.models.entities import Project, Script
from core.store.memory import MemoryStore
from core.store.persist import load_store, save_store, schedule_save

WS_SEND_TIMEOUT_SEC = float(os.getenv("SVG_WS_SEND_TIMEOUT_SEC", "2.0"))


def parse_a2ui_default_timeout(raw: str | None = None) -> float | None:
    """解析 SVG_A2UI_DEFAULT_TIMEOUT_SEC：空/0/none → 无限等待；正数 → 秒。"""
    if raw is None:
        raw = os.getenv("SVG_A2UI_DEFAULT_TIMEOUT_SEC", "")
    text = str(raw).strip().lower()
    if not text or text in ("none", "null", "off"):
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if value <= 0:
        return None
    return value


A2UI_DEFAULT_TIMEOUT_SEC = parse_a2ui_default_timeout()


class AppState:
    """FastAPI 应用单例状态容器。"""

    def __init__(self) -> None:
        perf_logger = logging.getLogger("apps.api.state")
        init_start = time.perf_counter()

        setup_logging()
        self.store = MemoryStore()
        self.conversation_index = ConversationIndex()
        self.conversation_sqlite = ConversationSqliteStore()
        self.conversation_write_queue = ConversationWriteQueue(self.conversation_sqlite)
        self.conversations = ConversationStore(
            sqlite_store=self.conversation_sqlite,
            write_queue=self.conversation_write_queue,
        )
        with PerfSpan("startup", "load_store", logger=perf_logger):
            load_store(
                self.store,
                conversation_index=self.conversation_index,
                conversation_store=self.conversations,
            )
        from core.store.persist import configure_persist_hooks

        configure_persist_hooks(
            conversation_index=self.conversation_index,
            conversation_store=self.conversations,
        )
        with PerfSpan("startup", "recover_stuck_scripts", logger=perf_logger):
            self._recover_stuck_executing_scripts()
        with PerfSpan("startup", "sync_conversation_stores", logger=perf_logger):
            self._sync_conversation_stores()
        self.llm_config = LLMConfigManager()
        self.ai_config = AiConfigManager(self.llm_config)
        self.agent_config = get_agent_config_manager()
        self.interaction_log_store = InteractionLogStore()
        self.interaction_file_store = InteractionFileStore()
        self.emitter = EventEmitter()
        self.interaction_recorder = InteractionRecorder(
            self.interaction_log_store,
            self.emitter,
            file_store=self.interaction_file_store,
            emit_ws_events=False,
        )
        from core.interaction_log.async_writer import configure_interaction_log_writer
        from core.interaction_log.media_log import bind_media_interaction_recorder

        bind_media_interaction_recorder(self.interaction_recorder)
        with PerfSpan("startup", "configure_interaction_log_writer", logger=perf_logger):
            configure_interaction_log_writer(
                self.interaction_log_store,
                self.interaction_file_store,
            )
        self.confirmation_manager = ConfirmationManager(
            self.emitter,
            sqlite_store=self.conversation_sqlite,
            default_timeout=A2UI_DEFAULT_TIMEOUT_SEC,
        )
        with PerfSpan("startup", "super_video_master_init", logger=perf_logger):
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
        self._chat_tasks: dict[str, asyncio.Task[None]] = {}

        total_ms = (time.perf_counter() - init_start) * 1000
        log_perf(
            "startup",
            "AppState 初始化完成",
            duration_ms=total_ms,
            logger=perf_logger,
            projects=len(self.store.projects),
            scripts=len(self.store.scripts),
            text_assets=len(self.store.text_assets),
            media_assets=len(self.store.media_assets),
        )

    def _recover_stuck_executing_scripts(self) -> None:
        """启动时修复磁盘上卡住的 executing 状态（无活跃取消注册时视为失败）。"""
        from core.execution.cancel import get_execution_cancel_registry
        from core.models.entities import ScriptStatus

        registry = get_execution_cancel_registry()
        recovered = False
        for script in self.store.scripts.values():
            if script.status != ScriptStatus.EXECUTING:
                continue
            if registry.is_active(script.id):
                continue
            script.status = ScriptStatus.FAILED
            recovered = True
        if recovered:
            save_store(
                self.store,
                conversation_index=self.conversation_index,
                conversation_store=None,
            )

    def _sync_conversation_stores(self) -> None:
        """双向同步：SQLite ↔ 内存 index / JSON 消息。"""
        added = self.conversation_index.merge_from_sqlite(self.conversation_sqlite)
        sqlite_ids = {c.id for c in self.conversation_sqlite.list_all_conversations()}
        for conv in list(self.conversation_index.conversations.values()):
            if conv.id not in sqlite_ids:
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
        for conv in list(self.conversation_index.conversations.values()):
            self.conversation_sqlite.upsert_conversation(conv)
        if self.conversations.messages:
            self.conversation_sqlite.backfill_messages(self.conversations.messages)
        kwargs = {
            "store": self.store,
            "conversation_index": self.conversation_index,
            "conversation_store": self.conversations,
        }
        if immediate:
            save_store(**kwargs)
        else:
            schedule_save(**kwargs)

    async def persist_store_async(self, *, immediate: bool = False) -> None:
        """在线程池中落盘，避免阻塞 asyncio 事件循环。"""
        await asyncio.to_thread(self.persist_store, immediate=immediate)

    def is_chat_running(self, script_id: str) -> bool:
        """判断剧本是否仍有进行中的后台 chat 任务。"""
        task = self._chat_tasks.get(script_id)
        return task is not None and not task.done()

    def register_chat_task(self, script_id: str, task: asyncio.Task[None]) -> None:
        """登记后台 chat 任务，便于查询活跃执行态。"""
        self._chat_tasks[script_id] = task

    def clear_chat_task(
        self, script_id: str, task: asyncio.Task[None] | None = None
    ) -> None:
        """后台 chat 结束后移除任务登记。

        若传入 ``task``，仅当它仍是当前登记任务时才移除，避免中止后新 chat
        已被登记时被旧任务的 finally 误清。
        """
        current = self._chat_tasks.get(script_id)
        if task is not None and current is not task:
            return
        self._chat_tasks.pop(script_id, None)

    def cancel_chat_task(self, script_id: str) -> bool:
        """对仍在运行的后台 chat 任务发出 asyncio.cancel，促使尽快收尾。"""
        task = self._chat_tasks.get(script_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def reload_agent_config(self) -> None:
        """从磁盘重载 Agent 配置，并同步到主编排与子 Agent 实例。"""
        self.agent_config.reload()
        self._sync_agent_config_refs()

    def _sync_agent_config_refs(self) -> None:
        """将共享 Agent 配置引用同步到运行时实例。"""
        master = self.super_video_master
        master._agent_config = self.agent_config
        registry = master._registry
        registry._agent_config = self.agent_config
        for agent in registry._agents.values():
            agent._agent_config = self.agent_config

    def channel_key(self, project_id: str, script_id: str) -> str:
        return f"{project_id}:{script_id}"

    async def broadcast(self, project_id: str, script_id: str, event: dict) -> None:
        channel = self.channel_key(project_id, script_id)
        for ws in self.ws_clients.get(channel, []):
            await ws.send_json(event)


state = AppState()


def _bind_generation_queue() -> None:
    """将全局生成队列接到 store 与 EventEmitter。"""
    from core.generation.queue import get_generation_queue
    from core.generation.runner import run_generation_job

    q = get_generation_queue()

    async def _runner(job):
        await run_generation_job(state.store, state.emitter, job)

    async def _on_change(script_id: str) -> None:
        snap = q.snapshot_for_script(script_id)
        await state.emitter.emit(snap)

    q.set_runner(_runner)
    q.set_on_change(_on_change)


_bind_generation_queue()

_GLOBAL_WS_BROADCAST_TYPES = {
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


async def _send_ws_event_bounded(ws: Any, event: dict) -> bool:
    """向单个 WebSocket 发送事件，超时或失败时返回 False。"""
    try:
        await asyncio.wait_for(ws.send_json(event), timeout=WS_SEND_TIMEOUT_SEC)
        return True
    except Exception:
        return False


def _collect_ws_broadcast_targets(
    script_id: str | None,
    event_type: str,
) -> list[tuple[str, Any]]:
    """收集应接收事件的 WebSocket 客户端列表。"""
    targets: list[tuple[str, Any]] = []
    if script_id:
        target_suffix = f":{script_id}"
        for channel, clients in list(state.ws_clients.items()):
            if channel.endswith(target_suffix):
                for ws in list(clients):
                    targets.append((channel, ws))
        return targets

    if not (
        event_type.startswith("a2ui_") or event_type in _GLOBAL_WS_BROADCAST_TYPES
    ):
        return targets

    for channel, clients in list(state.ws_clients.items()):
        for ws in list(clients):
            targets.append((channel, ws))
    return targets


def _prune_failed_ws_clients(
    targets: list[tuple[str, Any]],
    results: list[bool | BaseException],
) -> None:
    """移除发送失败或超时的 WebSocket 客户端，避免毒连接拖死广播。"""
    for (channel, ws), result in zip(targets, results):
        if result is True:
            continue
        clients = state.ws_clients.get(channel)
        if clients and ws in clients:
            clients.remove(ws)


async def _ws_emit_handler(event: dict) -> None:
    """将 EventEmitter 事件推送到 WebSocket 客户端（按 script_id 路由，避免跨剧本泄漏）。"""
    script_id = event.get("script_id")
    event_type = event.get("type", "")
    targets = _collect_ws_broadcast_targets(script_id, event_type)
    if not targets:
        return

    results = await asyncio.gather(
        *[_send_ws_event_bounded(ws, event) for _, ws in targets],
        return_exceptions=True,
    )
    normalized: list[bool | BaseException] = [
        r if isinstance(r, (bool, BaseException)) else False for r in results
    ]
    _prune_failed_ws_clients(targets, normalized)


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
    """创建剧本并写入创建时间，供整体看板按序编号。"""
    script = Script(
        project_id=project_id,
        title=title,
        duration_sec=duration_sec,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
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
