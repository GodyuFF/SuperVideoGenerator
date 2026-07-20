"""Tool 数据作用域与工具中心 API 字段测试。"""

from core.llm.tools.tool_data_scope import (
    EDIT_TIMELINE_WRITE_AGENT,
    resolve_tool_data_scope,
    tool_data_scope_view,
)


def test_sync_actual_assets_scope_no_timeline_write():
    """sync_actual_assets 数据边界不得包含剪辑时间轴写入。"""
    scope = resolve_tool_data_scope("storyboard_refine_agent", "sync_actual_assets")
    assert "剪辑时间轴" not in scope.write_entities
    view = tool_data_scope_view("storyboard_refine_agent", "sync_actual_assets")
    assert view["may_write_edit_timeline"] is False


def test_plan_edit_timeline_scope_allows_timeline_write():
    """plan_edit_timeline 为 editing_agent 唯一流水线创建入口。"""
    view = tool_data_scope_view("editing_agent", "plan_edit_timeline")
    assert view["may_write_edit_timeline"] is True
    assert "剪辑时间轴" in view["affected_data_write"]


def test_synthesize_scope_no_timeline_write():
    """TTS synthesize 仅写分镜与音频资产。"""
    view = tool_data_scope_view("tts_agent", "synthesize")
    assert view["may_write_edit_timeline"] is False
    assert "剪辑时间轴" not in view["affected_data_write"]


def test_edit_timeline_write_agent_constant():
    """剪辑时间轴写权限常量指向 editing_agent。"""
    assert EDIT_TIMELINE_WRITE_AGENT == "editing_agent"
