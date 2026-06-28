"""PromptBuilder 固定/动态组装测试。"""

import json

from core.prompt.builder import (
    build_action_system,
    build_action_user,
    build_react_json_user,
    render_template,
)
from core.prompt.registry import PromptProfile


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


def test_build_react_json_user_contains_dynamic_fields():
    payload = json.loads(
        build_react_json_user(
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


def test_build_action_system_includes_agent_actions():
    system = build_action_system("script_agent", PromptProfile.DEFAULT)
    assert "observation" in system
    assert "parse_brief" in system
    assert "asset_id" in system


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
