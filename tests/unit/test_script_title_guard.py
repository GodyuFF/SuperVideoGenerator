"""单元测试：剧本标题确认后的稳定性策略。"""

from core.guards.script_title import (
    apply_script_title_if_allowed,
    is_mutable_script_title,
)


def test_placeholder_titles_are_mutable():
    """默认/未命名等占位标题可被正式名替换。"""
    assert is_mutable_script_title("默认剧本")
    assert is_mutable_script_title("")
    assert is_mutable_script_title("未命名剧本")


def test_confirmed_title_is_immutable_for_agent():
    """已确认正式标题不可被 Agent 随意改写。"""
    assert not is_mutable_script_title("月光下的约定")
    assert apply_script_title_if_allowed("月光下的约定", "另一标题") is None


def test_message_preview_pollution_is_mutable():
    """历史用对话摘要污染的标题可被纠正。"""
    polluted = "重新设计剧本并加长旁白说明角色关系…"
    assert is_mutable_script_title(polluted)
    assert apply_script_title_if_allowed(polluted, "正式剧名") == "正式剧名"


def test_apply_allows_replace_placeholder():
    """占位标题可写入正式名。"""
    assert apply_script_title_if_allowed("默认剧本", "正式剧名") == "正式剧名"
