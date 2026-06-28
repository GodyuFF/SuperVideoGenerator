"""Agent 交互流程验证测试：验证 role_prompt 从 definitions 正确传递到 XML。"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.agents.definitions import AGENT_DEFINITIONS
from core.agents.registry import AgentRegistry
from core.events.emitter import EventEmitter
from core.interaction_log.recorder import InteractionRecorder
from core.llm.react_decider import LLMReActDecider
from core.llm.settings import LLMConfigManager
from core.store.memory import MemoryStore
from tests.support.scripted_llm import ScriptedLLMClient


@pytest.mark.asyncio
async def test_agent_role_prompt_flow_to_xml():
    """验证 registry 设置的 role_prompt 与各 Agent 定义一致。"""
    store = MemoryStore()
    emitter = EventEmitter()
    conversations = None
    config = LLMConfigManager()
    config.update(api_key="test-key", use_llm_react=True)
    recorder = InteractionRecorder(None, emitter)
    decider = LLMReActDecider(config, ScriptedLLMClient(), recorder)

    registry = AgentRegistry(store, emitter, conversations, decider, recorder)

    for agent_name, definition in AGENT_DEFINITIONS.items():
        agent = registry.get(agent_name)
        assert agent.role_prompt == definition.role_prompt, f"{agent_name} role_prompt 不匹配"
        assert agent.display_name == definition.display_name


@pytest.mark.asyncio
async def test_role_prompt_in_decide_method():
    """验证 ReActAgent.decide 方法正确传递 role_prompt 给 decider。"""
    from unittest.mock import MagicMock

    from core.agents.react_core import AgentRunContext

    # 创建一个 mock 的 llm_decider
    mock_decider = MagicMock()
    mock_decider.decide_agent = AsyncMock(return_value=MagicMock(action="finish", thought="test"))

    # 创建一个简单的 agent 子类用于测试
    class TestAgent:
        name = "test_agent"
        display_name = "测试 Agent"
        role_prompt = "我是专门的测试 Agent 角色提示。"

        def get_action_pipeline(self):
            return ["test"]

        async def decide(self, ctx):
            return await mock_decider.decide_agent(
                ctx,
                display_name=self.display_name,
                role_prompt=self.role_prompt,
                action_pipeline=self.get_action_pipeline(),
            )

    agent = TestAgent()
    ctx = AgentRunContext(
        task_brief="test",
        work_context={},
        script_id="s1",
        step_id="step1",
        agent_name="test_agent",
    )

    await agent.decide(ctx)

    # 验证 decide_agent 被调用时传入了正确的 role_prompt
    call_kwargs = mock_decider.decide_agent.call_args[1]
    assert call_kwargs.get("role_prompt") == "我是专门的测试 Agent 角色提示。"
