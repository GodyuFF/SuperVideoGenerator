"""pytest 共享 fixture。"""

import pytest

from core.llm.settings import LLMConfigManager
from core.models.entities import VideoStyleMode
from tests.support.scripted_llm import ScriptedLLMClient


@pytest.fixture
def llm_config_with_key():
    config = LLMConfigManager()
    config.update(api_key="test-scripted-key", use_llm_react=True)
    return config


def inject_scripted_llm(master, style_mode: VideoStyleMode = VideoStyleMode.DYNAMIC_IMAGE):
    """将 SuperVideoMaster 及其子 Agent 的 LLM 客户端替换为脚本化实现。"""
    scripted = ScriptedLLMClient(style_mode)
    master._llm_config.update(api_key="test-scripted-key", use_llm_react=True)
    master._llm_decider._client = scripted
    master._llm_client = scripted
    for agent in master._registry._agents.values():
        agent._llm_client = scripted
    return scripted


@pytest.fixture(autouse=True)
def patch_global_llm_for_tests(request):
    """API 与集成测试默认使用脚本化 LLM；@pytest.mark.live 走真实模型。"""
    if request.node.get_closest_marker("live"):
        yield
        return
    from apps.api.state import state

    inject_scripted_llm(state.super_video_master)
    yield
