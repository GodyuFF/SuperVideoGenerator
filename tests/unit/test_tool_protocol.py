"""parse_react_tool_calls 单元测试。"""

import json

import pytest

from core.llm.protocol import parse_react_json, parse_react_tool_calls
from core.llm.client.tool_calls import ToolCallResult


def test_parse_react_tool_calls():
    result = ToolCallResult(
        content="先写剧本",
        tool_calls=[{
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "delegate_script_design",
                "arguments": json.dumps({"note": "尽快"}),
            },
        }],
    )
    d = parse_react_tool_calls(result)
    assert d.thought == "先写剧本"
    assert d.action == "delegate_script_design"
    assert d.action_input == {"note": "尽快"}


def test_parse_react_tool_calls_missing_raises():
    with pytest.raises(ValueError, match="tool_calls"):
        parse_react_tool_calls(ToolCallResult(content="", tool_calls=[]))


def test_parse_react_json_legacy():
    d = parse_react_json(
        {"thought": "应先创建剧情", "action": "create_plot", "action_input": {}}
    )
    assert d.action == "create_plot"


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
