"""action_label 单元测试。"""

from core.llm.master import action_kind, action_label


def test_action_label_delegate():
    assert action_label("delegate_script_design") == "委派 · 剧本与文字资产设计"
    assert action_kind("delegate_script_design") == "delegate"


def test_action_label_tool():
    assert action_label("tool_get_plan_summary") == "调用工具 · 查询计划摘要"
    assert action_kind("tool_get_plan_summary") == "tool"


def test_action_label_finish():
    assert action_label("finish") == "结束编排"
    assert action_kind("finish") == "finish"
