"""LlmRequest 与 Anthropic wire 转换测试。"""

from core.llm.client.wire import (
    llm_request_to_anthropic_payload,
    llm_request_to_log_body,
    llm_request_to_wire_messages,
    tools_to_anthropic,
)
from core.llm.model.llm_request import LlmRequest, ToolDefinition
from core.llm.model.chat_message import (
    chat_message,
    text_block,
    tool_message,
    tool_use_block,
)
from core.llm.prompt.chat_messages import (
    apply_snippet_chat_history,
    build_llm_request,
    build_llm_request_ordered,
)


def assert_wire_tool_pairs_valid(wire: list[dict]) -> None:
    """断言 wire 中每个 tool_result 均有上一条 assistant 的匹配 tool_use。"""
    for index, msg in enumerate(wire):
        if msg.get("role") != "user":
            continue
        for block in msg.get("content", []):
            if block.get("type") != "tool_result":
                continue
            assert index > 0 and wire[index - 1].get("role") == "assistant"
            tool_use_ids = {
                b.get("id")
                for b in wire[index - 1].get("content", [])
                if b.get("type") == "tool_use"
            }
            assert block.get("tool_use_id") in tool_use_ids


def test_build_llm_request_excludes_system_from_messages():
    req = build_llm_request(
        system_prompt="你是助手",
        history=[chat_message("user", "你好")],
    )
    assert req.system == "你是助手"
    assert len(req.messages) == 1
    assert req.messages[0]["role"] == "user"
    assert all(m.get("role") != "system" for m in req.messages)


def test_log_body_separates_system_tools_messages():
    tool = ToolDefinition(
        name="parse_brief",
        description="解析简报",
        input_schema={"type": "object", "properties": {}},
    )
    req = LlmRequest(
        system="system text",
        tools=[tool],
        messages=[chat_message("user", "hi")],
        tool_choice={"type": "tool", "name": "parse_brief"},
    )
    body = llm_request_to_log_body(req, model="claude-sonnet", stream=True)
    assert body["system"] == "system text"
    assert body["messages"][0]["role"] == "user"
    assert body["tools"][0]["name"] == "parse_brief"
    assert "system" not in str(body["messages"][0].get("role"))
    assert body["tool_choice"]["name"] == "parse_brief"


def test_wire_payload_system_at_top_level():
    req = build_llm_request(
        system_prompt="sys",
        tools=[
            ToolDefinition(
                name="finish",
                description="结束",
                input_schema={"type": "object", "properties": {}},
            )
        ],
        history=[chat_message("user", "u1")],
    )
    payload = llm_request_to_anthropic_payload(
        req, model="m", temperature=0.1, max_tokens=100
    )
    assert payload["system"] == "sys"
    assert payload["messages"][0]["role"] == "user"
    assert payload["tools"][0]["name"] == "finish"
    assert payload["tools"][0]["input_schema"]["type"] == "object"


def test_tools_to_anthropic_maps_input_schema():
    tool = ToolDefinition(
        name="create_plot",
        description="创建剧情",
        input_schema={
            "type": "object",
            "properties": {"observation": {"type": "string"}},
            "required": ["observation"],
        },
    )
    wire = tools_to_anthropic([tool])[0]
    assert wire["name"] == "create_plot"
    assert wire["input_schema"]["required"] == ["observation"]


def test_wire_messages_exclude_system():
    req = build_llm_request_ordered(
        system_prompt="S",
        anchor_user="U",
    )
    wire = llm_request_to_wire_messages(req)
    assert wire[0]["role"] == "user"
    assert all(m.get("role") != "system" for m in wire)


def test_sub_agent_wire_e2e_with_compressed_history():
    """模拟子 Agent：anchor + 压缩历史 + turn_user，wire 无 orphan tool_result。"""
    history: list[dict] = [
        {
            "role": "assistant",
            "content": [
                tool_use_block(tool_id="call_1", name="scan_text_assets", input_data={}),
            ],
        },
        tool_message("call_1", "扫描完成 " + ("x" * 600)),
    ]
    for i in range(14):
        history.append(
            {"role": "assistant", "content": [text_block(f"轮次{i} " + ("y" * 400))]}
        )

    compressed = apply_snippet_chat_history(history)
    req = build_llm_request_ordered(
        system_prompt="你是 image_agent",
        anchor_user="任务简报：生图",
        history=compressed,
        turn_user="## 当前行动上下文\n{\"available_actions\": [\"finish\"]}",
    )
    wire = llm_request_to_wire_messages(req)
    assert_wire_tool_pairs_valid(wire)
    assert wire[0]["role"] == "user"
    assert "任务简报" in str(wire[0]["content"])
