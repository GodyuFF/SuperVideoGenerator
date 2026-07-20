"""主编排统一委派工具 delegate_agent 的候选解析与动态 schema。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.llm.master.actions import STEP_META

DELEGATE_AGENT_ACTION = "delegate_agent"


@dataclass(frozen=True)
class DelegateCandidate:
    """当前 Profile 与风格下可委派的子 Agent 候选。"""

    agent_id: str
    step_type: str
    display_name: str
    description: str
    title: str


def steps_for_style(
    style_mode: Any,
    *,
    config: Any | None = None,
) -> list[str]:
    """该风格下可能出现的流水线 step_type（稳定字母序）。"""
    from core.llm.style.style_mode_registry import StyleModeRegistry

    style_id = style_mode.value if hasattr(style_mode, "value") else str(style_mode)
    steps = [
        "edit_compose",
        "image_gen",
        "script_design",
        "shot_detail",
        "storyboard",
        "tts_gen",
    ]
    if StyleModeRegistry.style_includes_video_gen(style_id, config=config):
        steps.append("video_gen")
    return sorted(steps)


def build_delegate_agent_candidates(
    profile_id: str,
    style_mode: Any,
    *,
    config: Any | None = None,
) -> list[DelegateCandidate]:
    """按 Profile roster 与风格组装可委派子 Agent 列表。"""
    from core.llm.agent.agent_registry import resolve_display_name, resolve_roster_agent_for_step
    from core.llm.agent.config_manager import get_agent_config_manager

    mgr = config or get_agent_config_manager()
    allowed_steps = set(steps_for_style(style_mode, config=config))
    seen_agents: set[str] = set()
    result: list[DelegateCandidate] = []
    for step_type, meta in STEP_META.items():
        if step_type not in allowed_steps:
            continue
        target = resolve_roster_agent_for_step(step_type, profile_id, config=mgr)
        if not target or target in seen_agents:
            continue
        seen_agents.add(target)
        display = resolve_display_name(target, config=mgr, profile_id=profile_id)
        result.append(
            DelegateCandidate(
                agent_id=target,
                step_type=step_type,
                display_name=display if target != meta["agent"] else meta["title"],
                description=meta["description"],
                title=meta["title"],
            )
        )
    return sorted(result, key=lambda item: item.agent_id)


def delegate_agent_available(
    profile_id: str,
    style_mode: Any,
    *,
    config: Any | None = None,
) -> bool:
    """当前 Profile 与风格下是否存在可委派子 Agent。"""
    return bool(
        build_delegate_agent_candidates(profile_id, style_mode, config=config)
    )


def eligible_agent_ids_from_readiness(
    readiness: list[dict[str, Any]],
    completed_step_types: set[str] | None = None,
) -> list[str]:
    """从 delegate_readiness 解析本轮可委派的 agent_id（未完成且无硬拦）。"""
    completed = completed_step_types or set()
    out: list[str] = []
    for row in readiness:
        step_type = str(row.get("step_type") or "")
        agent_id = row.get("agent_id")
        if not agent_id or step_type in completed or row.get("hard_blockers"):
            continue
        out.append(str(agent_id))
    return sorted(set(out))


def build_sub_agents_orchestration_state(
    *,
    profile_id: str,
    style_mode: Any,
    completed_step_types: set[str],
    delegate_readiness: list[dict[str, Any]] | None = None,
    config: Any | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """组装主编排状态 JSON 用的 sub_agents 行与 available_sub_agents 列表。"""
    from core.llm.master.session import build_master_sub_agents

    readiness = delegate_readiness or []
    by_agent = {str(r["agent_id"]): r for r in readiness if r.get("agent_id")}
    by_step = {str(r["step_type"]): r for r in readiness if r.get("step_type")}
    rows: list[dict[str, Any]] = []
    for spec in build_master_sub_agents(profile_id=profile_id, config=config):
        row = by_agent.get(spec.agent_name) or by_step.get(spec.step_type) or {}
        completed = spec.step_type in completed_step_types
        hard_blockers = list(row.get("hard_blockers") or [])
        soft_blockers = list(row.get("soft_blockers") or [])
        available = not completed and not hard_blockers
        rows.append(
            {
                "agent_id": spec.agent_name,
                "step_type": spec.step_type,
                "display_name": spec.display_name,
                "description": spec.description,
                "depends_on": STEP_META.get(spec.step_type, {}).get("depends_on", ""),
                "produces": STEP_META.get(spec.step_type, {}).get("produces", ""),
                "ready": bool(row.get("ready")) if row else False,
                "soft_blockers": soft_blockers,
                "hard_blockers": hard_blockers,
                "completed": completed,
                "available": available,
            }
        )
    available_ids = [r["agent_id"] for r in rows if r.get("available")]
    return rows, available_ids


def build_delegate_agent_description(
    profile_id: str,
    style_mode: Any,
    *,
    config: Any | None = None,
    delegate_readiness: list[dict[str, Any]] | None = None,
    eligible_agent_ids: list[str] | None = None,
) -> str:
    """从配置/roster 组装 delegate_agent 工具 description（含本轮可委派标注）。"""
    candidates = build_delegate_agent_candidates(
        profile_id, style_mode, config=config
    )
    if not candidates:
        return "委派子 Agent 执行专项任务（当前 Profile 无可用子 Agent）。"
    readiness = delegate_readiness or []
    eligible = set(eligible_agent_ids or [])
    by_agent = {str(r["agent_id"]): r for r in readiness if r.get("agent_id")}
    lines = [
        "委派子 Agent 执行专项任务。传入 agent_id 选择目标（须为当前可委派 id）。",
        "硬性约束：本 tool 必须单独成轮，禁止与 tool_* / finish / ask_user_question 或其他 function 同轮并行。",
        "可选 agent_id：",
    ]
    for item in candidates:
        row = by_agent.get(item.agent_id) or {}
        suffix = ""
        if eligible:
            if item.agent_id in eligible:
                if row.get("soft_blockers"):
                    suffix = "【本轮可委派，但有软依赖提示】"
                else:
                    suffix = "【本轮可委派】"
            elif row.get("hard_blockers"):
                suffix = f"【不可委派：{row['hard_blockers'][0]}】"
            else:
                suffix = "【本轮不可委派：已完成或已阻塞】"
        lines.append(
            f"- {item.agent_id}（{item.display_name}）：{item.description}{suffix}"
        )
    if eligible:
        lines.append(f"当前可委派 agent_id：{', '.join(sorted(eligible))}")
    return "\n".join(lines)


def build_delegate_agent_input_schema(
    profile_id: str,
    style_mode: Any,
    *,
    config: Any | None = None,
    eligible_agent_ids: list[str] | None = None,
) -> dict[str, Any]:
    """按当前 roster 生成 delegate_agent 的 input_schema（enum 默认仅含本轮可委派 id）。"""
    from core.llm.tools.shared.input_common import REACT_INPUT_SCHEMA, merge_plan_tracking

    candidates = build_delegate_agent_candidates(
        profile_id, style_mode, config=config
    )
    roster_ids = [item.agent_id for item in candidates]
    agent_ids = list(eligible_agent_ids) if eligible_agent_ids is not None else roster_ids
    agent_ids = [aid for aid in agent_ids if aid in roster_ids]
    schema = merge_plan_tracking(dict(REACT_INPUT_SCHEMA))
    props = dict(schema.get("properties") or {})
    props["agent_id"] = {
        "type": "string",
        "enum": agent_ids if agent_ids else [],
        "description": "子 Agent 编码（须从 description 中「当前可委派 agent_id」选择）",
    }
    schema["properties"] = props
    required = list(schema.get("required") or [])
    if "agent_id" not in required:
        required.append("agent_id")
    schema["required"] = required
    return schema
