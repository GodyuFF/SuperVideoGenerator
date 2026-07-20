"""主编排同轮多 tool_* 并行落盘测试。"""

from core.conversation.store import ConversationStore, MessageRole
from core.llm.agent.react_core import ReActDecision, ToolCallDecision
from core.llm.master.master_react import MasterReActEngine
from core.llm.model.chat_message import normalize_content


def test_persist_master_react_turn_batch():
    """主编排 batch 落盘 1 assistant + N tool 消息并合并 observation。"""
    conversations = ConversationStore()
    engine = MasterReActEngine.__new__(MasterReActEngine)
    engine._conversations = conversations

    decision = ReActDecision(
        thought="并行查询",
        action="tool_list_assets",
        action_input={},
        calls=[
            ToolCallDecision("t1", "tool_list_assets", {"plan_status": "查资产", "remaining_plan": "继续"}),
            ToolCallDecision("t2", "tool_list_projects", {}),
        ],
    )
    results = [
        ("tool_list_assets", "t1", "资产列表 A"),
        ("tool_list_projects", "t2", "项目列表 B"),
    ]
    observation = engine._persist_master_react_turn_batch(
        "conv_master_batch",
        "proj1",
        "script1",
        decision,
        results,
    )
    assert "1. tool_list_assets: 资产列表 A" in observation
    assert "2. tool_list_projects: 项目列表 B" in observation

    msgs = conversations.list_messages("conv_master_batch", channel="master")
    assistant = next(m for m in msgs if m.role == MessageRole.ASSISTANT)
    tool_msgs = [m for m in msgs if m.role == MessageRole.TOOL]
    tool_uses = [
        b for b in normalize_content(assistant.content) if b.get("type") == "tool_use"
    ]
    assert len(tool_uses) == 2
    assert len(tool_msgs) == 2
    assert {m.tool_call_id for m in tool_msgs} == {"t1", "t2"}
