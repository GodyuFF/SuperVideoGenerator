"""Agent 交互流程验证测试。"""

import pytest

from core.llm.agent.definitions import AGENT_DEFINITIONS
from core.conversation import ConversationStore
from core.llm.agent.registry import AgentRegistry
from core.events.emitter import EventEmitter
from core.interaction_log.recorder import InteractionRecorder
from core.llm.client.settings import LLMConfigManager
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
    scripted = ScriptedLLMClient()
    registry = AgentRegistry(
        store, emitter, conversations, config, scripted, recorder
    )

    for agent_name, definition in AGENT_DEFINITIONS.items():
        agent = registry.get(agent_name)
        assert agent.role_prompt == definition.role_prompt, f"{agent_name} role_prompt 不匹配"
        assert agent.display_name == definition.display_name


@pytest.mark.asyncio
async def test_role_prompt_in_decide_method():
    """验证 ReActAgent.decide 将 resolve_role_prompt 结果传给 decide_sub_agent。"""
    from unittest.mock import AsyncMock, MagicMock, patch

    from core.llm.agent.react_core import AgentRunContext

    mock_decision = MagicMock(action="finish", thought="test")

    with patch(
        "core.llm.agent.base.decide_sub_agent", new_callable=AsyncMock
    ) as mock_decide:
        mock_decide.return_value = mock_decision

        store = MemoryStore()
        emitter = EventEmitter()
        config = LLMConfigManager()
        config.update(api_key="test-key", use_llm_react=True)
        scripted = ScriptedLLMClient()
        registry = AgentRegistry(
            store, emitter, ConversationStore(), config, scripted
        )
        agent = registry.get("script_agent")
        ctx = AgentRunContext(
            task_brief="test",
            work_context={},
            script_id="s1",
            step_id="step1",
            agent_name="script_agent",
        )
        await agent.decide(ctx)

        mock_decide.assert_awaited_once()
        kwargs = mock_decide.call_args.kwargs
        assert kwargs["role_prompt"] == agent.resolve_role_prompt(ctx)
        assert kwargs["display_name"] == agent.display_name
