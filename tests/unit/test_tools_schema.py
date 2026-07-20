"""tools_schema 单元测试。"""

from core.llm.tools.shared.agent_tools import (
    AGENT_TOOLS,
    ASK_USER_QUESTION_ACTION,
    ad_hoc_actions,
    pipeline_actions,
    read_actions,
)
from core.llm.prompt.tools.registry import (
    build_action_tool,
    build_master_react_tools,
    build_sub_agent_react_tools,
    tool_choice_force,
)
from core.llm.prompt.tools.schemas import action_input_schema

READ_ONLY_REQUIRED = ["observation", "plan_status", "remaining_plan"]


def _assert_read_only_plan_tracking(schema: dict) -> None:
    assert "plan_status" in schema["properties"]
    assert "remaining_plan" in schema["properties"]
    assert schema.get("additionalProperties") is True
    for key in READ_ONLY_REQUIRED:
        assert key in schema.get("required", []), f"missing required {key}"


def test_build_master_react_tools_includes_finish():
    tools = build_master_react_tools(
        ["delegate_agent", "finish"],
        profile_id="default",
        style_mode="storybook",
    )
    names = [t.name for t in tools]
    assert "delegate_agent" in names
    assert "finish" in names
    assert ASK_USER_QUESTION_ACTION in names


def test_build_master_delegate_is_agent_tool():
    tools = build_master_react_tools(
        ["delegate_agent"],
        profile_id="default",
        style_mode="storybook",
    )
    delegate = next(t for t in tools if t.name == "delegate_agent")
    assert delegate.kind == "agent"
    assert "agent_id" in delegate.input_schema["properties"]
    assert "script_agent" in delegate.input_schema["properties"]["agent_id"]["enum"]
    assert "plan_status" in delegate.input_schema["properties"]
    assert "remaining_plan" in delegate.input_schema["required"]
    assert "script_agent" in delegate.description


def test_react_input_schema_finish_requires_plan_fields():
    from core.llm.tools.schemas import react_input_schema

    schema = react_input_schema("finish")
    assert "plan_status" in schema["required"]
    assert "remaining_plan" in schema["required"]


def test_build_sub_agent_react_tools():
    tools = build_sub_agent_react_tools("script_agent", ["parse_brief", "finish"])
    names = [t.name for t in tools]
    assert "parse_brief" in names
    assert ASK_USER_QUESTION_ACTION in names


def test_build_action_tool_has_observation():
    tool = build_action_tool("script_agent", "create_plot")
    assert tool.name == "create_plot"
    props = tool.input_schema["properties"]
    assert "observation" in props
    assert "content" in props


def test_parse_brief_schema_has_content_md():
    schema = action_input_schema("parse_brief")
    props = schema["properties"]
    assert "content_md" in props
    assert "observation" in props
    assert "content_md" in schema.get("required", [])


def test_create_character_content_has_description():
    schema = action_input_schema("create_character")
    content = schema["properties"]["content"]
    assert "description" in content["properties"]
    assert "description" in content.get("required", [])
    assert "tts_voice" in content["properties"]
    assert "tts_voice" in content.get("required", [])


def test_update_character_requires_asset_id_and_partial_content():
    schema = action_input_schema("update_character")
    assert schema["required"] == ["observation", "asset_id", "content"]
    content = schema["properties"]["content"]
    assert content.get("minProperties") == 1
    assert "required" not in content or not content.get("required")
    assert "description" in content["properties"]
    assert "description" not in content.get("required", [])


def test_update_script_only_requires_observation():
    schema = action_input_schema("update_script")
    assert schema["required"] == ["observation"]
    assert "content_md" in schema["properties"]
    assert "content_md" not in schema.get("required", [])


def test_update_plot_content_is_partial():
    schema = action_input_schema("update_plot")
    content = schema["properties"]["content"]
    assert content.get("minProperties") == 1
    assert "text" in content["properties"]
    assert "required" not in content or content.get("required") == []


def test_read_only_tools_require_observation_and_plan_tracking():
    for action in ("get_plan", "list_images"):
        schema = action_input_schema(action)
        _assert_read_only_plan_tracking(schema)


def test_list_text_assets_input_schema():
    schema = action_input_schema("list_text_assets")
    _assert_read_only_plan_tracking(schema)
    props = schema["properties"]
    assert "types" in props
    assert "include_content" in props
    assert props["types"]["items"]["enum"] == ["character", "scene", "prop", "plot"]


def test_list_text_assets_output_schema_nested():
    from core.llm.tools.output_schemas import list_text_assets_output_schema

    schema = list_text_assets_output_schema()
    assert schema["required"] == [
        "script_id",
        "script",
        "count",
        "counts_by_type",
        "assets",
    ]
    asset_props = schema["properties"]["assets"]["items"]["properties"]
    assert "linked" in asset_props
    assert "counts_by_type" in schema["properties"]


def test_all_ad_hoc_actions_have_action_schema():
    for action in ad_hoc_actions("script_agent"):
        schema = action_input_schema(action)
        props = schema.get("properties") or {}
        assert "observation" in props, f"{action} 缺少 observation"
        assert "observation" in schema.get("required", []), f"{action} 未必填 observation"


def test_all_read_actions_have_action_schema():
    for agent_name in AGENT_TOOLS:
        for action in read_actions(agent_name):
            schema = action_input_schema(action)
            required = schema.get("required", [])
            assert "observation" in required, action
            if action == "read_webpage":
                assert "url" in required, action
            else:
                _assert_read_only_plan_tracking(schema)


def test_all_pipeline_actions_have_action_schema():
    for agent_name in (
        "script_agent",
        "image_agent",
        "storyboard_agent",
        "video_agent",
        "tts_agent",
        "editing_agent",
        "storyboard_refine_agent",
    ):
        for action in pipeline_actions(agent_name):
            schema = action_input_schema(action)
            props = schema.get("properties") or {}
            assert props, f"{agent_name}.{action} 缺少 properties"
            assert "observation" in props, f"{agent_name}.{action} 缺少 observation"


def test_tool_choice_force():
    assert tool_choice_force("parse_brief") == {
        "type": "tool",
        "name": "parse_brief",
    }


def test_registry_tools_have_output_schema():
    from core.llm.tools import get_tool_registry

    registry = get_tool_registry()
    for spec in registry.list_tools():
        assert spec.output_schema.get("type") == "object", spec.name


def test_update_clip_output_schema_not_asset_mutation():
    """update_clip 不得误用 asset_mutation output schema。"""
    from core.llm.tools.register_helpers import output_schema_for

    schema = output_schema_for("update_clip")
    required = schema.get("required", [])
    assert "action" in required
    assert "clip_id" in required
    assert "asset_id" not in required


def test_get_export_status_output_schema_no_action():
    """get_export_status 输出对齐 job_to_dict，不要求 action。"""
    from core.llm.tools.register_helpers import output_schema_for

    schema = output_schema_for("get_export_status")
    required = schema.get("required", [])
    assert "job_id" in required
    assert "action" not in required


def test_sub_agent_react_tools_unique_names_with_full_available():
    """模拟 decide_sub_agent 完整 available 列表，tools name 不得重复。"""
    agent = "script_agent"
    available = (
        pipeline_actions(agent)
        + ad_hoc_actions(agent)
        + read_actions(agent)
        + ["return_to_master", "finish"]
    )
    tools = build_sub_agent_react_tools(agent, available)
    names = [t.name for t in tools]
    assert len(names) == len(set(names)), f"duplicate tool names: {names}"
    assert "return_to_master" in names
    assert "finish" in names


def test_sub_agent_react_tools_use_full_input_schema():
    tools = build_sub_agent_react_tools("script_agent", ["create_character", "finish"])
    create = next(t for t in tools if t.name == "create_character")
    assert "content" in create.input_schema["properties"]
    assert create.output_schema.get("type") == "object"
