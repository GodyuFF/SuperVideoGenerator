"""LLM JSON 容错解析测试。"""

import json

import pytest

from core.llm.json_parse import parse_llm_json_object


def test_parse_standard_json():
    data = parse_llm_json_object('{"observation": "完成", "content": {"text": "a"}}')
    assert data["observation"] == "完成"


def test_parse_python_single_quote_dict():
    raw = "{'name': '密林深处', 'description': '阳光透过树冠'}"
    data = parse_llm_json_object(raw)
    assert data["name"] == "密林深处"


def test_parse_json_with_leading_whitespace():
    raw = "                              {'observation': '已创建场景'}"
    data = parse_llm_json_object(raw)
    assert data["observation"] == "已创建场景"


def test_parse_json_in_fence():
    raw = '```json\n{"action": "finish"}\n```'
    data = parse_llm_json_object(raw)
    assert data["action"] == "finish"


def test_parse_invalid_raises():
    with pytest.raises(ValueError, match="非合法 JSON"):
        parse_llm_json_object("not json at all")


def test_parse_tool_arguments_extra_trailing_brace():
    from core.llm.json_parse import parse_tool_arguments

    valid = {"observation": "ok", "remaining_plan": ["a"]}
    raw = json.dumps(valid, ensure_ascii=False) + "}"
    assert parse_tool_arguments(raw) == valid


def test_parse_tool_arguments_unescaped_quotes_in_text():
    from core.llm.json_parse import parse_tool_arguments

    raw = (
        '{"observation": "创建剧情", "asset_name": "开场", '
        '"content": {"text": "旁白：被誉为"森林之王"的老虎"}}'
    )
    data = parse_tool_arguments(raw)
    assert data["content"]["text"] == '旁白：被誉为"森林之王"的老虎'


def test_parse_tool_arguments_coerces_string_content_object():
    from core.llm.json_parse import parse_tool_arguments

    inner = {"summary": "东北虎", "description": "体型健硕", "prompt_hint": "侧面照"}
    raw = {
        "observation": "创建角色",
        "content": json.dumps(inner, ensure_ascii=False),
    }
    data = parse_tool_arguments(raw)
    assert data["content"] == inner


def test_parse_tool_arguments_salvages_truncated_generate_images():
    from core.llm.json_parse import parse_tool_arguments

    raw = (
        '{"observation": "扫描到7个待生图资产，开始批量生成。", "items": '
        '[{"asset_id": "txt_edeaa8918906", "name": "孟加拉虎", '
        '"image_prompt": "character portrait, full body or uppe'
    )
    data = parse_tool_arguments(raw)
    assert "扫描到7个" in data["observation"]
    assert "items" not in data


def test_parse_tool_arguments_rejects_placeholder_template():
    from core.llm.json_parse import parse_tool_arguments

    raw = '{"$PARAMETER_NAME": $PARAMETER_VALUE}'
    with pytest.raises(ValueError, match="非合法 JSON"):
        parse_tool_arguments(raw)

