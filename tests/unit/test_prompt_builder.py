"""PromptBuilder 固定/动态组装测试。"""

import json

from core.llm.prompt.builder import (
    build_action_context_turn_content,
    build_action_system,
    build_action_user,
    build_react_state_json,
    build_react_state_turn_content,
    render_template,
)
from core.llm.prompt.chat_messages import REACT_STATE_HEADER
from core.llm.prompt.registry import PromptProfile


def test_render_template_replaces_slots():
    text = render_template(
        "action_context.txt",
        {
            "display_name": "剧本 Agent",
            "role_prompt": "角色说明",
            "task_brief": "写剧本",
            "work_context_line": "script_id=s1",
            "store_context": "",
            "current_action": "parse_brief",
            "completed_actions": "无",
            "history_summary_block": "",
            "observations_block": "- 无",
        },
    )
    assert "剧本 Agent" in text
    assert "parse_brief" in text
    assert "{{" not in text


def test_build_react_state_json_contains_dynamic_fields():
    payload = json.loads(
        build_react_state_json(
            task_brief="设计剧本",
            available_actions=["parse_brief", "finish"],
            completed=[],
            observations=["观察1"],
            extra={"iteration": 1},
        )
    )
    assert payload["task_brief"] == "设计剧本"
    assert "parse_brief" in payload["available_actions"]
    assert "观察1" in payload["observations"]
    assert payload["iteration"] == 1


def test_build_react_state_json_excludes_completed_from_available():
    payload = json.loads(
        build_react_state_json(
            task_brief="设计剧本",
            available_actions=["parse_brief", "script_structure", "finish"],
            completed=["parse_brief"],
            observations=["观察1"],
        )
    )
    assert payload["completed_actions"] == ["parse_brief"]
    assert "parse_brief" not in payload["available_actions"]
    assert "script_structure" in payload["available_actions"]
    assert "finish" in payload["available_actions"]


def test_build_react_state_json_keeps_repeatable_create_actions():
    payload = json.loads(
        build_react_state_json(
            task_brief="设计剧本",
            available_actions=["create_plot", "create_character", "finish"],
            completed=["create_plot"],
            observations=[],
        )
    )
    assert "create_plot" in payload["completed_actions"]
    assert "create_plot" in payload["available_actions"]


def test_build_react_state_json_keeps_completed_master_tools_available():
    payload = json.loads(
        build_react_state_json(
            task_brief="查计划",
            available_actions=["tool_get_plan_summary", "finish"],
            completed=["tool:get_plan_summary"],
            observations=[],
        )
    )
    assert "tool:get_plan_summary" in payload["completed_actions"]
    assert "tool_get_plan_summary" in payload["available_actions"]


def test_build_action_system_includes_protocol():
    system = build_action_system("script_agent", PromptProfile.DEFAULT)
    assert "observation" in system
    assert "function" in system
    assert "本 Agent 行动字段" not in system


def test_build_react_static_system_includes_profile_hint():
    """子 Agent ReAct 静态 system 应合并 action_hint。"""
    from core.llm.prompt.builder import build_react_static_system
    from core.llm.prompt.registry import get_agent_role_prompt

    role = get_agent_role_prompt("storyboard_agent", PromptProfile.STORYBOOK)
    system = build_react_static_system(
        role,
        agent_name="storyboard_agent",
        profile=PromptProfile.STORYBOOK,
    )
    assert "audio_tracks" in system
    assert "模式补充" in system


def test_build_react_state_turn_content_includes_header_and_json():
    state_json = build_react_state_json(
        task_brief="设计剧本",
        available_actions=["finish"],
        completed=[],
    )
    turn = build_react_state_turn_content(state_json, hint="建议 finish")
    assert REACT_STATE_HEADER in turn
    assert state_json in turn
    assert "建议 finish" in turn


def test_build_action_context_turn_content():
    inner = build_action_user(
        {
            "display_name": "图片 Agent",
            "role_prompt": "# Identity",
            "task_brief": "生图",
            "work_context_line": "project_id=p1",
            "store_context": "",
            "current_action": "scan_text_assets",
            "completed_actions": "无",
            "history_summary_block": "",
            "observations_block": "- 无",
        }
    )
    turn = build_action_context_turn_content(inner)
    assert "## 当前行动上下文" in turn
    assert "scan_text_assets" in turn


def test_build_action_user_from_slots():
    text = build_action_user(
        {
            "display_name": "图片 Agent",
            "role_prompt": "# Identity",
            "task_brief": "生图",
            "work_context_line": "project_id=p1",
            "store_context": "",
            "current_action": "scan_text_assets",
            "completed_actions": "无",
            "history_summary_block": "",
            "observations_block": "- 无",
        }
    )
    assert "scan_text_assets" in text
