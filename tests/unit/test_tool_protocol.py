"""parse_react_tool_calls 单元测试。"""

import json

import pytest

from core.llm.protocol import parse_react_tool_calls, parse_react_tool_calls_batch
from core.llm.client.tool_calls import ToolCallResult


def test_parse_react_tool_calls():
    result = ToolCallResult(
        content="先写剧本",
        tool_calls=[{
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "delegate_agent",
                "arguments": json.dumps({"agent_id": "script_agent", "note": "尽快"}),
            },
        }],
    )
    d = parse_react_tool_calls(result)
    assert d.thought == "先写剧本"
    assert d.action == "delegate_agent"
    assert d.action_input == {"agent_id": "script_agent", "note": "尽快"}


def test_parse_react_tool_calls_missing_raises():
    with pytest.raises(ValueError, match="tool_calls"):
        parse_react_tool_calls(ToolCallResult(content="", tool_calls=[]))


def test_parse_react_tool_calls_extra_trailing_brace():
    payload = {"observation": "创建道具", "asset_name": "野鹿"}
    result = ToolCallResult(
        content="创建道具",
        tool_calls=[{
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "create_prop",
                "arguments": json.dumps(payload, ensure_ascii=False) + "}",
            },
        }],
    )
    d = parse_react_tool_calls(result)
    assert d.action == "create_prop"
    assert d.action_input == payload


def test_parse_react_tool_calls_batch_multiple_creates():
    """解析全部 tool_calls 并保留 LLM 原始 id。"""
    result = ToolCallResult(
        content="批量创建资产",
        tool_calls=[
            {
                "id": "call_char",
                "type": "function",
                "function": {
                    "name": "create_character",
                    "arguments": json.dumps({"asset_name": "Alice", "plan_status": "进行中", "remaining_plan": "建道具"}),
                },
            },
            {
                "id": "call_prop",
                "type": "function",
                "function": {
                    "name": "create_prop",
                    "arguments": json.dumps({"asset_name": "Sword"}),
                },
            },
        ],
    )
    d = parse_react_tool_calls_batch(result, channel="sub_agent")
    assert d.is_batch is True
    assert len(d.calls) == 2
    assert d.calls[0].tool_call_id == "call_char"
    assert d.calls[1].tool_call_id == "call_prop"
    assert d.action == "create_character"
    assert d.calls[1].action_input == {"asset_name": "Sword"}


def test_parse_react_tool_calls_batch_rejects_delegate_mix():
    result = ToolCallResult(
        content="错误组合",
        tool_calls=[
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "delegate_agent", "arguments": "{}"},
            },
            {
                "id": "c2",
                "type": "function",
                "function": {"name": "tool_list_assets", "arguments": "{}"},
            },
        ],
    )
    with pytest.raises(ValueError, match="不可与其他 tool 同轮调用"):
        parse_react_tool_calls_batch(result, channel="master")


def test_parse_react_tool_calls_batch_sequential_mode():
    """非并行安全组合解析为 sequential batch_mode。"""
    result = ToolCallResult(
        content="先解析再创建",
        tool_calls=[
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "parse_brief", "arguments": "{}"},
            },
            {
                "id": "c2",
                "type": "function",
                "function": {
                    "name": "create_character",
                    "arguments": json.dumps({"asset_name": "Alice"}),
                },
            },
        ],
    )
    d = parse_react_tool_calls_batch(result, channel="sub_agent")
    assert d.is_batch is True
    assert d.batch_mode == "sequential"
    assert d.calls[0].action == "parse_brief"
    assert d.calls[1].action == "create_character"
