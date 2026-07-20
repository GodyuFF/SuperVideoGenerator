"""子 Agent ReAct 同轮多 tool 并行/顺序执行测试。"""

import asyncio

import pytest

from core.conversation.store import ConversationStore, MessageRole
from core.events.emitter import EventEmitter
from core.llm.agent.react_core import (
    AgentRunContext,
    ReActDecision,
    ReActRunner,
    ToolCallDecision,
)
from core.llm.model.chat_message import normalize_content


@pytest.mark.asyncio
async def test_react_runner_batch_parallel_act_and_persist():
    """同轮 3 个 create_* 并行 act，落盘 1 assistant + 3 tool 消息。"""
    emitter = EventEmitter()
    conversations = ConversationStore()
    runner = ReActRunner(emitter, conversations)
    act_calls: list[str] = []
    turn = {"n": 0}

    async def decide(_ctx: AgentRunContext) -> ReActDecision:
        turn["n"] += 1
        if turn["n"] == 1:
            return ReActDecision(
                thought="批量创建",
                action="create_character",
                action_input={},
                calls=[
                    ToolCallDecision("c1", "create_character", {"asset_name": "Alice"}),
                    ToolCallDecision("c2", "create_prop", {"asset_name": "Sword"}),
                    ToolCallDecision("c3", "create_scene", {"asset_name": "Forest"}),
                ],
                batch_mode="parallel",
            )
        return ReActDecision(
            thought="完成",
            action="finish",
            action_input={"observation": "全部完成"},
        )

    async def act(action: str, _ctx: AgentRunContext) -> str:
        act_calls.append(action)
        return f"ok:{action}"

    await runner.run_agent(
        agent_name="script_agent",
        display_name="剧本 Agent",
        task_brief="批量建资产",
        work_context={
            "project_id": "proj_batch",
            "script_id": "script_batch",
            "conversation_id": "conv_batch",
        },
        script_id="script_batch",
        step_id="step_batch",
        decide=decide,
        act=act,
    )

    assert sorted(act_calls) == sorted(
        ["create_character", "create_prop", "create_scene"]
    )
    msgs = conversations.list_messages("conv_batch", channel="agent", agent_name="script_agent")
    assistant_msgs = [m for m in msgs if m.role == MessageRole.ASSISTANT]
    tool_msgs = [m for m in msgs if m.role == MessageRole.TOOL]
    assert len(assistant_msgs) >= 2
    batch_assistant = next(
        m
        for m in assistant_msgs
        if len([b for b in normalize_content(m.content) if b.get("type") == "tool_use"]) == 3
    )
    tool_blocks = [
        b for b in normalize_content(batch_assistant.content) if b.get("type") == "tool_use"
    ]
    assert {b.get("name") for b in tool_blocks} == {
        "create_character",
        "create_prop",
        "create_scene",
    }
    assert len(tool_msgs) >= 3
    paired_ids = {m.tool_call_id for m in tool_msgs if m.tool_call_id}
    assert {"c1", "c2", "c3"}.issubset(paired_ids)


@pytest.mark.asyncio
async def test_react_runner_batch_sequential_preserves_order():
    """非白名单同轮 tool 按返回顺序串行执行。"""
    emitter = EventEmitter()
    conversations = ConversationStore()
    runner = ReActRunner(emitter, conversations)
    act_order: list[str] = []
    gate = asyncio.Event()
    turn = {"n": 0}

    async def decide(_ctx: AgentRunContext) -> ReActDecision:
        """首轮返回顺序 batch，次轮 finish。"""
        turn["n"] += 1
        if turn["n"] == 1:
            return ReActDecision(
                thought="先解析再创建",
                action="parse_brief",
                action_input={},
                calls=[
                    ToolCallDecision("s1", "parse_brief", {}),
                    ToolCallDecision("s2", "create_character", {"asset_name": "Bob"}),
                ],
                batch_mode="sequential",
            )
        return ReActDecision(
            thought="完成",
            action="finish",
            action_input={"observation": "完成"},
        )

    async def act(action: str, _ctx: AgentRunContext) -> str:
        """记录执行顺序；顺序模式下后者须等前者完成。"""
        if action == "parse_brief":
            act_order.append(action)
            gate.set()
            await asyncio.sleep(0.05)
            return "ok:parse_brief"
        await gate.wait()
        act_order.append(action)
        return f"ok:{action}"

    await runner.run_agent(
        agent_name="script_agent",
        display_name="剧本 Agent",
        task_brief="顺序执行",
        work_context={
            "project_id": "proj_seq",
            "script_id": "script_seq",
            "conversation_id": "conv_seq",
        },
        script_id="script_seq",
        step_id="step_seq",
        decide=decide,
        act=act,
    )

    assert act_order == ["parse_brief", "create_character"]
    msgs = conversations.list_messages("conv_seq", channel="agent", agent_name="script_agent")
    tool_msgs = [m for m in msgs if m.role == MessageRole.TOOL]
    paired_ids = {m.tool_call_id for m in tool_msgs if m.tool_call_id}
    assert {"s1", "s2"}.issubset(paired_ids)
