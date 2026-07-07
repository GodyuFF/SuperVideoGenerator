"""单元测试：ReAct 核心与子 Agent ReAct。"""

import pytest

from core.conversation.store import ConversationStore, MessageKind
from core.llm.agent.react_core import AgentRunContext
from core.llm.agent.registry import AgentRegistry
from core.events.emitter import EventEmitter
from core.llm.client import LLMClient
from core.llm.react_decide import decide_sub_agent, require_llm
from core.llm.client.settings import LLMConfigManager
from core.logging.setup import setup_logging
from core.models.entities import Project, Script
from core.store.memory import MemoryStore
from tests.support.scripted_llm import ScriptedLLMClient


@pytest.mark.asyncio
async def test_script_agent_react_isolated(llm_config_with_key):
    """剧本 Agent 在隔离会话中通过 LLM ReAct 执行。"""
    setup_logging("WARNING")
    store = MemoryStore()
    emitter = EventEmitter()
    conversations = ConversationStore()
    scripted = ScriptedLLMClient()
    registry = AgentRegistry(
        store, emitter, conversations, llm_config_with_key, scripted
    )
    agent = registry.get("script_agent")

    project = Project(title="测试")
    store.add_project(project)
    script = Script(project_id=project.id, title="S1")
    store.add_script(script)

    events = []

    async def capture(e):
        events.append(e)

    emitter.subscribe(capture)

    outputs = await agent.run(
        task_brief="生成都市题材剧本与文字资产。",
        work_context={
            "project_id": project.id,
            "script_id": script.id,
            "conversation_id": "conv-test",
        },
        script_id=script.id,
        step_id="step_test",
    )

    assert len(outputs) >= 3
    msgs = conversations.list_messages("conv-test", "agent", "script_agent")
    assert any(
        m.message_kind == MessageKind.TASK_BRIEF for m in msgs
    )
    assert any(m.role.value == "assistant" for m in msgs)
    assert any(m.role.value == "tool" for m in msgs)
    assert any(e.get("type") == "agent_react_finished" for e in events)


@pytest.mark.asyncio
async def test_decider_requires_llm():
    """未配置 API Key 时应拒绝决策。"""
    config = LLMConfigManager()
    config.update(use_llm_react=False)
    with pytest.raises(RuntimeError, match="LLM"):
        require_llm(config)

    ctx = AgentRunContext(
        task_brief="t",
        work_context={},
        script_id="s1",
        step_id="step1",
        agent_name="script_agent",
    )
    with pytest.raises(RuntimeError, match="LLM"):
        await decide_sub_agent(
            LLMClient(config),
            config,
            ctx,
            conversations=ConversationStore(),
            display_name="剧本 Agent",
            role_prompt="角色",
            action_pipeline=["parse_brief"],
        )


@pytest.mark.asyncio
async def test_decide_sub_agent_state_json_in_last_turn_user(llm_config_with_key):
    """子 Agent ReAct：任务简报为首条 user，编排状态 JSON 在末条 user。"""
    from core.llm.client.tool_calls import ToolCallResult
    from core.llm.model.chat_message import message_content_text
    from core.llm.prompt.chat_messages import REACT_STATE_HEADER, extract_react_state_json
    from core.llm.react_decide import decide_sub_agent
    from tests.support.scripted_llm import _make_tool_call

    captured: list = []
    client = ScriptedLLMClient()

    async def capture(request, **kwargs):
        captured.append(request)
        return ToolCallResult(
            content="完成",
            tool_calls=[_make_tool_call("finish", {})],
            raw_message={"role": "assistant", "content": "完成", "tool_calls": []},
        )

    client.complete_tool_calls = capture  # type: ignore[method-assign]

    ctx = AgentRunContext(
        task_brief="生成都市题材剧本与文字资产。",
        work_context={"project_id": "p1", "script_id": "s1", "conversation_id": "conv-order"},
        script_id="s1",
        step_id="step1",
        agent_name="script_agent",
        conversation_id="conv-order",
        project_id="p1",
    )
    await decide_sub_agent(
        client,
        llm_config_with_key,
        ctx,
        conversations=ConversationStore(),
        display_name="剧本 Agent",
        role_prompt="角色",
        action_pipeline=["parse_brief"],
    )
    assert captured
    req = captured[0]
    assert req.messages[0]["role"] == "user"
    assert "生成都市题材剧本" in message_content_text(req.messages[0]["content"])
    assert REACT_STATE_HEADER not in (req.system or "")
    last_user = message_content_text(req.messages[-1]["content"])
    assert REACT_STATE_HEADER in last_user
    state = extract_react_state_json(req)
    assert state is not None
    assert "available_actions" in state
