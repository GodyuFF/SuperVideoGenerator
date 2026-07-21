"""Plan 模式运行时上下文：快照、切片与 LLM 回写解析。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from core.logging.setup import get_logger
from core.models.entities import PlanDocument, PlanStep, StepStatus

logger = get_logger("core.llm.plan_context")

PLAN_STATUS_HISTORY_MAX = 3
PLAN_STATUS_CHAR_BUDGET = 1200


@dataclass
class PlanUpdate:
    """LLM 单轮 plan 回写字段。"""

    plan_status: str
    remaining_plan: list[str] = field(default_factory=list)


class PlanSlice(BaseModel):
    """子 Agent 可见的全局计划切片。"""

    goal: str = ""
    current_step: dict[str, Any] | None = None
    completed_steps: list[dict[str, Any]] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    last_remaining_plan: list[str] = Field(default_factory=list)


def _step_brief(step: PlanStep) -> dict[str, Any]:
    return {
        "id": step.id,
        "type": step.type,
        "title": step.title,
        "status": step.status.value if hasattr(step.status, "value") else str(step.status),
        "agent": step.agent,
        "progress": step.progress,
    }


def build_plan_snapshot(plan: PlanDocument | None) -> dict[str, Any]:
    """紧凑 PlanDocument 快照，供主编排 LLM 上下文注入。"""
    if plan is None:
        return {"version": 0, "goal": "", "constraints": {}, "steps": [], "runtime_summary": ""}
    return {
        "version": plan.version,
        "goal": plan.goal,
        "constraints": dict(plan.constraints or {}),
        "runtime_summary": getattr(plan, "runtime_summary", "") or "",
        "steps": [_step_brief(s) for s in plan.steps],
    }


def build_plan_slice_for_step(
    plan: PlanDocument | None,
    step: PlanStep | None,
    last_remaining_plan: list[str] | None = None,
) -> PlanSlice:
    """为子 Agent 构造当前步骤相关的计划切片。"""
    if plan is None:
        return PlanSlice(last_remaining_plan=list(last_remaining_plan or []))
    completed = [
        _step_brief(s)
        for s in plan.steps
        if s.status in (StepStatus.COMPLETED, StepStatus.AWAITING_CONFIRMATION)
        and (step is None or s.id != step.id)
    ]
    current = _step_brief(step) if step else None
    return PlanSlice(
        goal=plan.goal,
        current_step=current,
        completed_steps=completed,
        constraints=dict(plan.constraints or {}),
        last_remaining_plan=list(last_remaining_plan or []),
    )


def normalize_remaining_plan(value: Any) -> list[str]:
    """将 remaining_plan 规范为字符串列表（兼容 JSON 数组字符串与换行分隔文本）。"""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return normalize_remaining_plan(parsed)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return lines or [text]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    text = str(value).strip()
    return [text] if text else []


def coerce_plan_tracking_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """将 plan_status / remaining_plan 规范为 schema 期望类型，容错 LLM 把数组写成 JSON 字符串。"""
    out = dict(arguments or {})
    if "remaining_plan" in out:
        out["remaining_plan"] = normalize_remaining_plan(out.get("remaining_plan"))
    if "plan_status" in out and out["plan_status"] is not None and not isinstance(
        out["plan_status"], str
    ):
        out["plan_status"] = str(out["plan_status"]).strip()
    return out


def extract_plan_update(action_input: dict[str, Any] | None) -> PlanUpdate | None:
    """从 tool arguments 提取 plan 回写；缺字段时返回 None 并记录 warning。"""
    if not action_input:
        logger.warning("plan_update missing: empty action_input")
        return None
    status = str(action_input.get("plan_status", "")).strip()
    remaining_raw = action_input.get("remaining_plan")
    if not status:
        logger.warning("plan_update missing: plan_status")
        return None
    return PlanUpdate(
        plan_status=status,
        remaining_plan=normalize_remaining_plan(remaining_raw),
    )


def format_plan_observation(update: PlanUpdate) -> str:
    """子 Agent plan 回写写入 observation 的格式。"""
    remaining = "；".join(update.remaining_plan) if update.remaining_plan else "无"
    return f"[plan] {update.plan_status} | 后续：{remaining}"


def trim_plan_status_history(history: list[str], *, max_items: int = PLAN_STATUS_HISTORY_MAX) -> list[str]:
    """保留最近 plan_status 条目，并按字符预算截断。"""
    if not history:
        return []
    recent = history[-max_items:]
    total = 0
    kept: list[str] = []
    for item in reversed(recent):
        text = item.strip()
        if not text:
            continue
        add = len(text) + (1 if kept else 0)
        if kept and total + add > PLAN_STATUS_CHAR_BUDGET:
            break
        kept.insert(0, text)
        total += add
    return kept or [recent[-1][:PLAN_STATUS_CHAR_BUDGET]]


def apply_plan_update_to_document(
    plan: PlanDocument,
    update: PlanUpdate,
) -> PlanDocument:
    """将 LLM plan 回写合并进 PlanDocument。"""
    plan.runtime_summary = update.plan_status
    return plan


def _resolve_step(
    plan: PlanDocument,
    *,
    step_id: str = "",
    step_type: str = "",
) -> PlanStep | None:
    """按 id 或 type 定位步骤（type 取第一个匹配）。"""
    sid = (step_id or "").strip()
    if sid:
        for step in plan.steps:
            if step.id == sid:
                return step
    stype = (step_type or "").strip()
    if stype:
        for step in plan.steps:
            if step.type == stype:
                return step
    return None


def _parse_step_status(raw: Any) -> StepStatus | None:
    """解析步骤状态字符串。"""
    text = str(raw or "").strip().lower()
    if not text:
        return None
    try:
        return StepStatus(text)
    except ValueError:
        return None


def apply_replan_op(plan: PlanDocument, op: dict[str, Any]) -> list[str]:
    """对 PlanDocument 应用单条 replan op，返回受影响 step_id 列表。"""
    kind = str(op.get("op", "")).strip()
    step = _resolve_step(
        plan,
        step_id=str(op.get("step_id", "")),
        step_type=str(op.get("step_type", "")),
    )
    if step is None:
        return []
    if kind == "skip":
        step.status = StepStatus.SKIPPED
        return [step.id]
    if kind == "reset_pending":
        step.status = StepStatus.PENDING
        step.progress = 0
        step.error = None
        return [step.id]
    if kind == "set_status":
        status = _parse_step_status(op.get("status"))
        if status is None:
            return []
        step.status = status
        return [step.id]
    if kind == "set_title":
        title = str(op.get("title", "")).strip()
        if not title:
            return []
        step.title = title
        return [step.id]
    return []


def apply_replan_to_document(
    plan: PlanDocument,
    update: PlanUpdate,
    *,
    reason: str,
    goal: str | None = None,
    ops: list[dict[str, Any]] | None = None,
    upsert_steps: list[dict[str, Any]] | None = None,
) -> tuple[PlanDocument, list[str]]:
    """应用结构化 replan：version++、ops、upsert，返回 (plan, affected_ids)。"""
    from core.models.entities import PlanStep

    affected: list[str] = []
    for raw in ops or []:
        if not isinstance(raw, dict):
            continue
        affected.extend(apply_replan_op(plan, raw))
    existing_types = {s.type for s in plan.steps}
    for raw in upsert_steps or []:
        if not isinstance(raw, dict):
            continue
        stype = str(raw.get("type", "")).strip()
        title = str(raw.get("title", "")).strip()
        agent = str(raw.get("agent", "")).strip()
        if not stype or not title or not agent:
            continue
        if stype in existing_types:
            step = _resolve_step(plan, step_type=stype)
            if step is None:
                continue
            step.title = title
            step.agent = agent
            desc = str(raw.get("description", "")).strip()
            if desc:
                step.description = desc
            status = _parse_step_status(raw.get("status"))
            if status is not None:
                step.status = status
            affected.append(step.id)
            continue
        status = _parse_step_status(raw.get("status")) or StepStatus.PENDING
        step = PlanStep(
            type=stype,
            title=title,
            agent=agent,
            description=str(raw.get("description", "") or ""),
            status=status,
        )
        plan.steps.append(step)
        existing_types.add(stype)
        affected.append(step.id)
    # 去重保序
    seen: set[str] = set()
    unique_affected: list[str] = []
    for sid in affected:
        if sid not in seen:
            seen.add(sid)
            unique_affected.append(sid)
    plan.version = int(plan.version or 0) + 1
    if goal:
        plan.goal = goal
    plan.runtime_summary = update.plan_status
    plan.last_replan_reason = reason.strip()
    plan.affected_step_ids = list(unique_affected)
    return plan, unique_affected
