"""执行模式辅助：目标模式（全自主）判定。"""

from __future__ import annotations

from core.models.entities import ExecutionMode, Project


def resolve_execution_mode(
    project: Project | None,
    *,
    override: ExecutionMode | None = None,
) -> ExecutionMode:
    if override is not None:
        return override
    if project is None:
        return ExecutionMode.INTERACTIVE
    return project.config.generation.execution_mode


def is_goal_mode(
    project: Project | None,
    *,
    override: ExecutionMode | None = None,
) -> bool:
    return resolve_execution_mode(project, override=override) == ExecutionMode.GOAL
