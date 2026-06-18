"""单元测试：纯净 ReAct 类。"""

import pytest

from core.agents.react_core import ReActDecision
from core.llm.react import (
    ReAct,
    ReActAgentInfo,
    ReActToolInfo,
    new_conversation_id,
)
from core.llm.settings import LLMConfigManager
from core.llm.xml_protocol import build_pure_react_xml


def test_pure_react_constructor_and_ai_config():
    config = LLMConfigManager()
    config.update(use_llm_react=False)
    agent = ReActAgentInfo(
        name="test_agent",
        display_name="测试 Agent",
        description="用于单元测试",
    )
    tools = [
        ReActToolInfo(
            action_name="tool_ping",
            name="ping",
            description="返回 pong",
        )
    ]
    react = ReAct.from_ai_config(
        agent_name="test_agent",
        conversation_id="conv_unit",
        agent=agent,
        tools=tools,
        llm_config=config,
        task_brief="测试任务",
    )
    assert react.agent_name == "test_agent"
    assert react.conversation_id == "conv_unit"
    assert react.agent.display_name == "测试 Agent"
    assert len(react.tools) == 1
    assert react.ai_config["use_llm_react"] is False
    assert "finish" in react.available_actions()


def test_build_pure_react_xml_fields():
    agent = ReActAgentInfo("a1", "A1", "desc")
    tools = [ReActToolInfo("tool_x", "x", "tool desc")]
    xml = build_pure_react_xml(
        conversation_id="conv_x",
        agent_name="a1",
        agent=agent,
        tools=tools,
        task_brief="brief",
        available_actions=["tool_x", "finish"],
        completed=[],
        observations=[],
    )
    assert "<conversation_id>conv_x</conversation_id>" in xml
    assert "<agent_name>a1</agent_name>" in xml
    assert "<action>tool_x</action>" in xml


@pytest.mark.asyncio
async def test_pure_react_run_with_handler():
    config = LLMConfigManager()
    config.update(use_llm_react=False)

    actions_run: list[str] = []

    async def on_action(action: str, action_input: dict) -> str:
        actions_run.append(action)
        if action == "tool_ping":
            return "pong"
        return "done"

    def fallback(react: ReAct) -> ReActDecision:
        if "tool_ping" not in react.completed:
            return ReActDecision(thought="先 ping", action="tool_ping")
        return ReActDecision(thought="结束", action="finish")

    react = ReAct(
        agent_name="test",
        conversation_id=new_conversation_id(),
        agent=ReActAgentInfo("test", "Test", "d"),
        tools=[ReActToolInfo("tool_ping", "ping", "ping tool")],
        llm_config=config,
        fallback=fallback,
    )
    history = await react.run(on_action)

    assert actions_run == ["tool_ping"]
    assert len(history) == 2
    assert history[0].action == "tool_ping"
    assert history[0].observation == "pong"
    assert history[1].action == "finish"


@pytest.mark.asyncio
async def test_pure_react_decide_fallback_without_key():
    config = LLMConfigManager()
    config.update(use_llm_react=False)
    react = ReAct(
        agent_name="test",
        conversation_id="conv_fb",
        agent=ReActAgentInfo("test", "T", "d"),
        tools=[],
        extra_actions=["act_a"],
        llm_config=config,
        fallback=lambda r: ReActDecision(thought="fb", action="finish"),
    )
    decision = await react.decide()
    assert decision.action == "finish"
    assert decision.thought == "fb"
