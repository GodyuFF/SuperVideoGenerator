"""pytest 共享 fixture。"""

import pytest

pytest_plugins = ["tests.support.timeline_store_fixture"]

from core.llm.a2ui.schemas import A2UIConfirmationResponse
from core.llm.client.settings import LLMConfigManager
from core.models.entities import VideoStyleMode
from tests.support.data_isolation import (
    cleanup_projects_by_ids,
    rebind_data_root,
    reset_app_state_for_tests,
    resolve_real_data_root,
    session_should_skip_isolation,
    snapshot_project_ids,
)
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


def inject_scripted_llm(master, style_mode: VideoStyleMode = VideoStyleMode.STORYBOOK):
    """将 SuperVideoMaster 及其子 Agent 的 LLM 客户端替换为脚本化实现。"""
    scripted = ScriptedLLMClient(style_mode)
    master._llm_config.update(api_key="test-scripted-key", use_llm_react=True)
    master._llm_client = master._react._llm_client = scripted
    for agent in master._registry._agents.values():
        agent._llm_client = scripted
    return scripted


@pytest.fixture(scope="session", autouse=True)
def isolate_test_data_session(request, tmp_path_factory):
    """会话级 data/ 隔离；结束后删除泄漏到真实 data/ 的测试项目。"""
    if session_should_skip_isolation(request.session):
        yield
        return

    real_root = resolve_real_data_root()
    baseline_ids = snapshot_project_ids(real_root)

    session_root = tmp_path_factory.mktemp("svg_pytest_data")
    rebind_data_root(session_root)
    reset_app_state_for_tests()

    yield

    leaked = snapshot_project_ids(real_root) - baseline_ids
    if leaked:
        cleanup_projects_by_ids(leaked, real_root)


@pytest.fixture(autouse=True)
def reset_ffmpeg_export_policy(monkeypatch):
    """每个测试默认关闭服务端 FFmpeg 成片导出（Classic 浏览器导出为唯一路径）。"""
    monkeypatch.delenv("SVG_EXPORT_ENABLED", raising=False)
    from core.edit import export_settings

    export_settings.reset_export_manager()
    yield
    export_settings.reset_export_manager()


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
    from core.rag.settings import reset_embedding_manager

    reset_embedding_manager()
    config_path = tmp_path / "ai_config.json"
    monkeypatch.setattr("core.llm.ai_config.DEFAULT_PATH", config_path)
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


@pytest.fixture(autouse=True)
def disable_rag_by_default(request, monkeypatch):
    """除 RAG 专测外，关闭项目 RAG 避免单元测试调用真实 embedding。"""
    if request.module.__name__ == "test_rag_shared_reuse":
        yield
        return
    from core.store.memory import MemoryStore

    original = MemoryStore.add_project

    def add_project_with_rag_off(self, project):
        project.config.rag.enabled = False
        return original(self, project)

    monkeypatch.setattr(MemoryStore, "add_project", add_project_with_rag_off)
    yield


@pytest.fixture(autouse=True)
def reset_agent_storage_between_tests(request):
    """每个用例重置会话内 agents 目录与 ConfigManager 单例，避免 roster 跨测试污染。"""
    if request.node.get_closest_marker("live"):
        yield
        return
    import shutil

    from core.llm.agent.config_manager import set_agent_config_manager
    from core.store.project_paths import resolve_data_root

    agents_dir = resolve_data_root() / "agents"
    if agents_dir.exists():
        shutil.rmtree(agents_dir)
    set_agent_config_manager(None)
    yield
    set_agent_config_manager(None)
