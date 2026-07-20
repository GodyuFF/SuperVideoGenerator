"""action_label 单元测试。"""

from core.llm.master import action_kind, action_label


def test_action_label_delegate():
    assert action_label("delegate_agent", agent_id="script_agent") == "委派 · 剧本 Agent"
    assert action_kind("delegate_agent") == "delegate"
    assert action_label("delegate_agent") == "委派 · 子 Agent"


def test_action_label_tool():
    assert action_label("tool_get_plan_summary") == "调用工具 · 查询计划摘要"
    assert action_kind("tool_get_plan_summary") == "tool"


def test_action_label_finish():
    assert action_label("finish") == "结束编排"
    assert action_kind("finish") == "finish"
