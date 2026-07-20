"""计划步骤终态解析单元测试。"""

from core.llm.master.plan_resolution import (
    has_blocking_plan_failures,
    is_plan_effectively_complete,
    is_step_superseded,
    plan_progress_counts,
)
from core.models.entities import PlanStep, StepStatus


def _step(step_type: str, status: StepStatus, title: str = "") -> PlanStep:
    """构造测试用 PlanStep。"""
    return PlanStep(
        type=step_type,
        title=title or step_type,
        agent="agent",
        status=status,
    )


def test_superseded_failed_image_gen_counts_as_recovered():
    """同类型后续成功时，中间 image_gen 失败应视为已恢复。"""
    steps = [
        _step("script_design", StepStatus.COMPLETED),
        _step("storyboard", StepStatus.COMPLETED),
        _step("image_gen", StepStatus.FAILED, "首次配图"),
        _step("image_gen", StepStatus.COMPLETED, "重试配图"),
        _step("video_gen", StepStatus.COMPLETED),
        _step("edit_compose", StepStatus.COMPLETED),
    ]
    assert is_step_superseded(steps, 2) is True
    assert has_blocking_plan_failures(steps) is False
    assert is_plan_effectively_complete(steps) is True
    done, total = plan_progress_counts(steps)
    assert done == total == 6


def test_unrecovered_failed_step_blocks_completion():
    """无后续成功覆盖时，失败步骤仍阻塞完成判定。"""
    steps = [
        _step("script_design", StepStatus.COMPLETED),
        _step("image_gen", StepStatus.FAILED),
        _step("video_gen", StepStatus.COMPLETED),
    ]
    assert is_step_superseded(steps, 1) is False
    assert has_blocking_plan_failures(steps) is True
    assert is_plan_effectively_complete(steps) is False
    done, total = plan_progress_counts(steps)
    assert done == 2
    assert total == 3


def test_skipped_last_occurrence_counts_as_complete():
    """同类型最后一步为 skipped 时仍视为完成。"""
    steps = [
        _step("script_design", StepStatus.COMPLETED),
        _step("video_gen", StepStatus.SKIPPED),
    ]
    assert is_plan_effectively_complete(steps) is True
