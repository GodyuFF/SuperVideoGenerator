"""pytest 共享 fixture。"""

import pytest

pytest_plugins = ["tests.support.timeline_store_fixture"]

from core.llm.a2ui.schemas import A2UIConfirmationResponse
from core.llm.client.settings import LLMConfigManager
from core.models.entities import VideoStyleMode
from tests.support.scripted_llm import ScriptedLLMClient


def setup_auto_confirm(emitter, confirmation) -> None:
    """测试环境自动批准 A2UI 确认，避免阻塞流水线。"""

    async def auto_approve(event: dict) -> None:
        if event.get("type") != "a2ui_confirmation_required":
            return
        kind = str(event.get("kind", ""))
        if kind == "script_structure":
            values: dict = {"intent": "continue", "feedback": ""}
        elif kind == "generic":
            values = {}
            for comp in event.get("components") or []:
                if not isinstance(comp, dict):
                    continue
                cid = comp.get("id")
                if not cid:
                    continue
                component = comp.get("component", "text")
                if component == "checkbox":
                    values[str(cid)] = bool(comp.get("value", False))
                else:
                    values[str(cid)] = comp.get("value", "")
        else:
            values = {"intent": "continue", "feedback": "", "confirm_checkbox": True}
        confirmation.resolve(
            A2UIConfirmationResponse(
                confirmation_id=str(event["confirmation_id"]),
                approved=True,
                values=values,
            )
        )

    emitter.subscribe(auto_approve)


@pytest.fixture
def llm_config_with_key():
    config = LLMConfigManager()
    config.update(api_key="test-scripted-key", use_llm_react=True)
    return config


def inject_scripted_llm(master, style_mode: VideoStyleMode = VideoStyleMode.DYNAMIC_IMAGE):
    """将 SuperVideoMaster 及其子 Agent 的 LLM 客户端替换为脚本化实现。"""
    scripted = ScriptedLLMClient(style_mode)
    master._llm_config.update(api_key="test-scripted-key", use_llm_react=True)
    master._llm_client = master._react._llm_client = scripted
    for agent in master._registry._agents.values():
        agent._llm_client = scripted
    return scripted


@pytest.fixture(autouse=True)
def patch_global_llm_for_tests(request, tmp_path, monkeypatch):
    """API 与集成测试默认使用脚本化 LLM；@pytest.mark.live 走真实模型。"""
    if request.node.get_closest_marker("live"):
        yield
        return
    from apps.api.state import state
    from core.llm.ai_config import AiConfigManager
    from core.llm.client.settings import LLMConfigManager
    from core.llm.tools.image.settings import ImageGenConfigManager, reset_image_gen_settings
    from core.llm.tools.tts.settings import TtsConfigManager, reset_tts_manager
    from core.llm.tools.video.settings import VideoGenConfigManager, reset_video_gen_manager

    reset_image_gen_settings()
    reset_video_gen_manager()
    reset_tts_manager()
    config_path = tmp_path / "ai_config.json"
    monkeypatch.setattr("core.llm.ai_config.DEFAULT_PATH", config_path)
    projects_root = tmp_path / "projects"
    projects_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("core.store.project_paths.PROJECTS_ROOT", projects_root)
    state.ai_config = AiConfigManager(
        LLMConfigManager(),
        ImageGenConfigManager(),
        VideoGenConfigManager(),
        TtsConfigManager(),
        path=config_path,
    )

    inject_scripted_llm(state.super_video_master)
    setup_auto_confirm(state.emitter, state.confirmation_manager)
    yield
