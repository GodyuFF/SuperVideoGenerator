"""update_plan / replan 工具处理器。"""

from __future__ import annotations

from typing import Any

from core.llm.agent.react_core import AgentRunContext
from core.llm.model.plan_context import (
    apply_plan_update_to_document,
    apply_replan_to_document,
    extract_plan_update,
    format_plan_observation,
)
from core.llm.tools.result import ToolResult
from core.store.memory import MemoryStore


def handle_update_plan(
    store: MemoryStore,
    ctx: AgentRunContext,
    arguments: dict[str, Any],
) -> ToolResult:
    """轻量回写 plan_status / remaining_plan，不提升 PlanDocument.version。"""
    update = extract_plan_update(arguments)
    if update is None:
        return ToolResult(
            observation="update_plan 需要非空 plan_status 与 remaining_plan。",
            structured={"ok": False, "error": "missing_plan_fields"},
            ok=False,
        )
    script_id = ctx.script_id
    plan = store.get_plan(script_id)
    if plan is not None:
        apply_plan_update_to_document(plan, update)
        store.set_plan(script_id, plan)
    obs = format_plan_observation(update)
    return ToolResult(
        observation=obs,
        structured={
            "action": "update_plan",
            "ok": True,
            "plan_status": update.plan_status,
            "remaining_plan": list(update.remaining_plan),
            "version": plan.version if plan else None,
        },
        ok=True,
    )


def handle_replan(
    store: MemoryStore,
    ctx: AgentRunContext,
    arguments: dict[str, Any],
) -> ToolResult:
    """结构化重规划：version++、应用 ops、写回 store。"""
    update = extract_plan_update(arguments)
    if update is None:
        return ToolResult(
            observation="replan 需要非空 plan_status 与 remaining_plan。",
            structured={"ok": False, "error": "missing_plan_fields"},
            ok=False,
        )
    reason = str(arguments.get("reason", "")).strip()
    if not reason:
        return ToolResult(
            observation="replan 需要非空 reason。",
            structured={"ok": False, "error": "missing_reason"},
            ok=False,
        )
    script_id = ctx.script_id
    plan = store.get_plan(script_id)
    if plan is None:
        return ToolResult(
            observation="当前尚无 PlanDocument，无法 replan。",
            structured={"ok": False, "error": "no_plan"},
            ok=False,
        )
    goal = arguments.get("goal")
    goal_text = str(goal).strip() if goal is not None else None
    ops = arguments.get("ops") or []
    if not isinstance(ops, list):
        ops = []
    upsert = arguments.get("upsert_steps") or []
    if not isinstance(upsert, list):
        upsert = []
    plan, affected = apply_replan_to_document(
        plan,
        update,
        reason=reason,
        goal=goal_text or None,
        ops=ops,
        upsert_steps=upsert,
    )
    store.set_plan(script_id, plan)
    script = store.scripts.get(script_id)
    if script is not None:
        script.plan_version = plan.version
    obs = (
        f"[replan] v{plan.version}：{reason}；"
        f"受影响步骤 {len(affected)} 个。"
        f" {format_plan_observation(update)}"
    )
    return ToolResult(
        observation=obs,
        structured={
            "action": "replan",
            "ok": True,
            "version": plan.version,
            "reason": reason,
            "affected_step_ids": affected,
            "plan_status": update.plan_status,
            "remaining_plan": list(update.remaining_plan),
            "plan": plan.model_dump(),
        },
        ok=True,
    )
