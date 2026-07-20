"""执行计划步骤终态解析：中间失败但后续同类型重试成功时视为已恢复。"""

from __future__ import annotations

from core.models.entities import PlanStep, StepStatus

_TERMINAL_OK = frozenset({StepStatus.COMPLETED, StepStatus.SKIPPED})


def is_step_superseded(steps: list[PlanStep], index: int) -> bool:
    """判断某失败步骤是否已被后续同类型成功步骤覆盖。"""
    if index < 0 or index >= len(steps):
        return False
    step = steps[index]
    if step.status != StepStatus.FAILED:
        return False
    step_type = step.type
    for later in steps[index + 1 :]:
        if later.type == step_type and later.status in _TERMINAL_OK:
            return True
    return False


def last_status_by_step_type(steps: list[PlanStep]) -> dict[str, StepStatus]:
    """按步骤顺序记录各 type 最后一次出现的状态。"""
    last: dict[str, StepStatus] = {}
    for step in steps:
        last[step.type] = step.status
    return last


def has_blocking_plan_failures(steps: list[PlanStep]) -> bool:
    """是否存在未被后续成功覆盖的失败步骤。"""
    for index, step in enumerate(steps):
        if step.status == StepStatus.FAILED and not is_step_superseded(steps, index):
            return True
    return False


def is_plan_effectively_complete(steps: list[PlanStep]) -> bool:
    """计划是否可视为完成：各 step type 最后一次状态均为 completed/skipped。"""
    if not steps:
        return False
    last = last_status_by_step_type(steps)
    return bool(last) and all(status in _TERMINAL_OK for status in last.values())


def plan_progress_counts(steps: list[PlanStep]) -> tuple[int, int]:
    """统计计划进度：已恢复的失败步骤计入完成数。"""
    total = len(steps)
    if total == 0:
        return 0, 0
    done = sum(
        1
        for index, step in enumerate(steps)
        if step.status in _TERMINAL_OK or is_step_superseded(steps, index)
    )
    return done, total
