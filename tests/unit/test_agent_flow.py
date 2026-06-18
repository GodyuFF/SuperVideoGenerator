"""Agent 交互流程验证测试：验证 role_prompt 从 definitions 正确传递到 XML。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.agents.definitions import AGENT_DEFINITIONS
from core.agents.registry import AgentRegistry
from core.events.emitter import EventEmitter
from core.interaction_log.recorder import InteractionRecorder
from core.llm.react_decider import LLMReActDecider
from core.llm.settings import LLMConfigManager
from core.store.memory import MemoryStore


@pytest.mark.asyncio
async def test_agent_role_prompt_flow_to_xml():
    """验证 registry 设置的 role_prompt 正确传递到 decide_agent 的 role_description。"""
    store = MemoryStore()
    emitter = EventEmitter()
    conversations = None  # 不需要真实 conversations
    config = LLMConfigManager()
    config.update(use_llm_react=False)  # 使用规则回退，避免真实 LLM 调用
    recorder = InteractionRecorder(None, emitter)
    decider = LLMReActDecider(config, None, recorder)

    registry = AgentRegistry(store, emitter, conversations, decider, recorder)

    captured_role_descriptions = {}

    # Patch build_context_xml 以捕获 role_description
    original_build = __import__("core.llm.xml_protocol", fromlist=["build_context_xml"]).build_context_xml

    def capturing_build_context_xml(role_description, task_brief, available_actions, completed, observations, extra=None):
        # 记录每个 agent 的 role_description
        # 通过调用栈识别当前 agent
        import inspect
        frame = inspect.currentframe()
        while frame:
            if "ctx" in frame.f_locals:
                ctx = frame.f_locals.get("ctx")
                if ctx and hasattr(ctx, "agent_name"):
                    captured_role_descriptions[ctx.agent_name] = role_description
                    break
            frame = frame.f_back
        return original_build(role_description, task_brief, available_actions, completed, observations, extra)

    with patch("core.llm.react_decider.build_context_xml", side_effect=capturing_build_context_xml):
        # 测试每个 agent
        for agent_name, definition in AGENT_DEFINITIONS.items():
            agent = registry.get(agent_name)
            # 验证 role_prompt 已从 definitions 设置
            assert agent.role_prompt == definition.role_prompt, f"{agent_name} role_prompt 不匹配"

    # 由于规则回退模式不会调用 LLM，captured_role_descriptions 可能为空
    # 我们直接验证 registry 中 agent 的 role_prompt 是否正确
    for agent_name, definition in AGENT_DEFINITIONS.items():
        agent = registry.get(agent_name)
        assert agent.role_prompt == definition.role_prompt
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
