"""Plan 模式上下文与 LLM 回写解析测试。"""

from core.llm.model.plan_context import (
    PlanSlice,
    PlanUpdate,
    apply_plan_update_to_document,
    build_plan_slice_for_step,
    build_plan_snapshot,
    extract_plan_update,
    format_plan_observation,
    normalize_remaining_plan,
    trim_plan_status_history,
)
from core.models.entities import PlanDocument, PlanStep, StepStatus


def test_build_plan_snapshot_empty():
    snap = build_plan_snapshot(None)
    assert snap["version"] == 0
    assert snap["steps"] == []


def test_build_plan_snapshot_with_steps():
    plan = PlanDocument(
        version=2,
        goal="测试视频",
        steps=[
            PlanStep(type="script_design", title="剧本", agent="script_agent", status=StepStatus.COMPLETED),
            PlanStep(type="image_gen", title="生图", agent="image_agent", status=StepStatus.PENDING),
        ],
    )
    snap = build_plan_snapshot(plan)
    assert snap["version"] == 2
    assert len(snap["steps"]) == 2
    assert snap["steps"][0]["status"] == "completed"


def test_build_plan_slice_for_step():
    step = PlanStep(type="image_gen", title="生图", agent="image_agent")
    plan = PlanDocument(
        goal="G",
        steps=[
            PlanStep(type="script_design", title="剧本", agent="script_agent", status=StepStatus.COMPLETED),
            step,
        ],
    )
    sl = build_plan_slice_for_step(plan, step, ["storyboard_agent"])
    assert sl.goal == "G"
    assert sl.current_step["type"] == "image_gen"
    assert len(sl.completed_steps) == 1
    assert sl.last_remaining_plan == ["storyboard_agent"]


def test_extract_plan_update():
    upd = extract_plan_update(
        {"plan_status": "剧本已完成", "remaining_plan": ["生图", "分镜"]}
    )
    assert upd is not None
    assert upd.plan_status == "剧本已完成"
    assert upd.remaining_plan == ["生图", "分镜"]


def test_extract_plan_update_missing():
    assert extract_plan_update({"remaining_plan": ["x"]}) is None
    assert extract_plan_update({}) is None


def test_normalize_remaining_plan_string():
    assert normalize_remaining_plan("a\nb") == ["a", "b"]


def test_format_plan_observation():
    text = format_plan_observation(PlanUpdate("完成生图", ["分镜"]))
    assert text.startswith("[plan]")
    assert "完成生图" in text


def test_trim_plan_status_history():
    history = [f"状态{i}" for i in range(10)]
    trimmed = trim_plan_status_history(history, max_items=3)
    assert len(trimmed) <= 3


def test_apply_plan_update_to_document():
    plan = PlanDocument(goal="G")
    apply_plan_update_to_document(plan, PlanUpdate("进行中", ["下一步"]))
    assert plan.runtime_summary == "进行中"
