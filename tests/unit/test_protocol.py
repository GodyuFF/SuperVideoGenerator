"""JSON ReAct 协议解析单元测试。"""

import pytest

from core.llm.protocol import parse_react_json


def test_parse_react_json_from_dict():
    d = parse_react_json(
        {"thought": "应先创建剧情", "action": "create_plot", "action_input": {}}
    )
    assert d.thought == "应先创建剧情"
    assert d.action == "create_plot"


def test_parse_react_json_from_string():
    raw = '{"thought":"完成","action":"finish","action_input":{}}'
    d = parse_react_json(raw)
    assert d.action == "finish"


def test_parse_react_json_invalid_raises():
    with pytest.raises(ValueError):
        parse_react_json("not json at all")
