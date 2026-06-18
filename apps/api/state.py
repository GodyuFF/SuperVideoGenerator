"""应用全局状态：存储、超级视频大师、WebSocket 客户端、A2UI 确认管理器。"""

from datetime import datetime, timezone

from core.a2ui.manager import ConfirmationManager
from core.agents.conversation import ConversationStore
from core.interaction_log.recorder import InteractionRecorder
from core.interaction_log.store import InteractionLogStore
from core.llm.settings import LLMConfigManager
from core.super_video_master.super_video_master import SuperVideoMaster
from core.events.emitter import EventEmitter
from core.logging.setup import setup_logging
from core.models.entities import Project, Script
from core.store.memory import MemoryStore


class AppState:
    """FastAPI 应用单例状态容器。"""

    def __init__(self) -> None:
        setup_logging()
        self.store = MemoryStore()
        self.conversations = ConversationStore()
        self.llm_config = LLMConfigManager()
        self.interaction_log_store = InteractionLogStore()
        self.emitter = EventEmitter()
        self.interaction_recorder = InteractionRecorder(
            self.interaction_log_store, self.emitter
        )
        self.confirmation_manager = ConfirmationManager(self.emitter)
        self.super_video_master = SuperVideoMaster(
            self.store,
            self.emitter,
            self.confirmation_manager,
            self.conversations,
            self.llm_config,
            self.interaction_recorder,
        )
        self.ws_clients: dict[str, list] = {}

    def channel_key(self, project_id: str, script_id: str) -> str:
        return f"{project_id}:{script_id}"

    async def broadcast(self, project_id: str, script_id: str, event: dict) -> None:
        channel = self.channel_key(project_id, script_id)
        for ws in self.ws_clients.get(channel, []):
            await ws.send_json(event)


state = AppState()


async def _ws_emit_handler(event: dict) -> None:
    script_id = event.get("script_id")
    for channel, clients in state.ws_clients.items():
        if script_id and channel.endswith(f":{script_id}"):
            for ws in clients:
                await ws.send_json(event)
        elif event.get("type", "").startswith("a2ui_") or event.get("type") in (
            "master_message",
            "interaction_log",
        ):
            for ws in clients:
                await ws.send_json(event)


state.emitter.subscribe(_ws_emit_handler)


def create_project(title: str) -> Project:
    project = Project(title=title, created_at=datetime.now(timezone.utc).isoformat())
    state.store.add_project(project)
    return project


def create_script(project_id: str, title: str, duration_sec: int = 60) -> Script:
    script = Script(project_id=project_id, title=title, duration_sec=duration_sec)
    state.store.add_script(script)
    return script
