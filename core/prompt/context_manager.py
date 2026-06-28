"""每 Agent 独立的动态上下文槽位管理。"""

from typing import Any

from core.agents.react_core import AgentRunContext
from core.prompt.context_window import PreparedContext
from core.store.memory import MemoryStore


def _format_work_context(work_context: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("script_id", "project_id", "style_mode"):
        if key in work_context:
            val = work_context[key]
            if hasattr(val, "value"):
                val = val.value
            parts.append(f"{key}={val}")
    return ", ".join(parts)


def _format_observations_block(observations: list[str]) -> str:
    lines = [f"- {o}" for o in observations] if observations else ["- 无"]
    return "\n".join(lines)


def _format_history_block(history_summary: str) -> str:
    if not history_summary.strip():
        return ""
    return f"较早上下文摘要：\n{history_summary.strip()}\n\n"


class SubAgentContextProvider:
    """子 Agent 动态上下文：ReAct 决策与行动执行各一套槽位。"""

    @staticmethod
    def build_react_extra(ctx: AgentRunContext) -> dict[str, Any]:
        extra: dict[str, Any] = {
            "agent": ctx.agent_name,
            "step_id": ctx.step_id,
            "iteration": ctx.iteration,
        }
        if ctx.work_context.get("style_mode") is not None:
            sm = ctx.work_context["style_mode"]
            extra["style_mode"] = str(sm.value if hasattr(sm, "value") else sm)
        if ctx.history_summary:
            extra["history_summary"] = ctx.history_summary
        return extra

    @staticmethod
    def build_react_inputs(
        ctx: AgentRunContext,
        *,
        role_prompt: str,
        display_name: str,
        available_actions: list[str],
    ) -> dict[str, Any]:
        observations = ctx.llm_observations or ctx.observations
        return {
            "task_brief": ctx.task_brief,
            "available_actions": available_actions,
            "completed": list(ctx.completed_actions),
            "observations": observations,
            "extra": SubAgentContextProvider.build_react_extra(ctx),
        }

    @staticmethod
    def build_action_slots(
        ctx: AgentRunContext,
        store: MemoryStore,
        *,
        role_prompt: str,
        display_name: str,
        action: str,
        store_context_block: str,
    ) -> dict[str, str]:
        observations = ctx.llm_observations or ctx.observations
        done = ", ".join(sorted(ctx.completed_actions)) or "无"
        return {
            "display_name": display_name,
            "role_prompt": role_prompt,
            "task_brief": ctx.task_brief,
            "work_context_line": _format_work_context(ctx.work_context),
            "store_context": store_context_block,
            "current_action": action,
            "completed_actions": done,
            "history_summary_block": _format_history_block(ctx.history_summary),
            "observations_block": _format_observations_block(observations),
        }


class MasterContextProvider:
    """主编排 ReAct 动态上下文。"""

    @staticmethod
    def apply_prepared(session: Any, prepared: PreparedContext) -> None:
        session.observations = list(prepared.observations)
        if prepared.history_summary:
            session.extra = dict(session.extra or {})
            session.extra["history_summary"] = prepared.history_summary


class AgentContextManager:
    """统一入口：按 agent 类型分发上下文 Provider。"""

    sub_agent = SubAgentContextProvider
    master = MasterContextProvider
