"""Skill tool_manifest 与 available_actions 过滤。"""

from core.extensions.tool_filter import apply_skill_tool_filter
from core.llm.tools.shared.agent_tools import ASK_USER_QUESTION_ACTION


def test_skill_whitelist_preserves_finish_and_ask():
    overlay = {
        "tool_manifest": {
            "agents": {"script_agent": ["list_text_assets"]},
        }
    }
    actions = ["parse_brief", "list_text_assets", "finish", ASK_USER_QUESTION_ACTION]
    filtered = apply_skill_tool_filter("script_agent", actions, overlay)
    assert "finish" in filtered
    assert ASK_USER_QUESTION_ACTION in filtered
    assert "parse_brief" not in filtered
    assert "list_text_assets" in filtered


def test_exclude_removes_globally():
    overlay = {"tool_manifest": {"exclude": ["delete_plot"]}}
    actions = ["parse_brief", "delete_plot", "list_text_assets"]
    filtered = apply_skill_tool_filter("script_agent", actions, overlay)
    assert "delete_plot" not in filtered
    assert "parse_brief" in filtered
