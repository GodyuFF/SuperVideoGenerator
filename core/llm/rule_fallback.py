"""规则回退：无 API Key 或 LLM 失败时使用。"""

from core.agents.react_core import AgentRunContext, MasterRunContext, ReActDecision
from core.super_video_master.actions import ACTION_TO_STEP, STEP_META, pipeline_for_style


def rule_decide_master(ctx: MasterRunContext) -> ReActDecision:
    pipeline = pipeline_for_style(ctx.style_mode)
    for action in pipeline:
        step_type = ACTION_TO_STEP[action]
        if step_type not in ctx.completed_step_types:
            meta = STEP_META[step_type]
            done = ", ".join(sorted(ctx.completed_step_types)) or "无"
            preview = ctx.user_message.replace("\n", " ")
            if len(preview) > 40:
                preview = preview[:40] + "…"
            if step_type == "script_design":
                thought = (
                    f"用户诉求摘要「{preview}」（用户原文仅保留在主会话）。"
                    f"已完成：{done}。应委派「{meta['title']}」。"
                )
            else:
                thought = (
                    f"已完成：{done}。下一步委派「{meta['title']}」"
                    f"（{meta['description']}）。"
                )
            return ReActDecision(thought=thought, action=action)
    summary = (
        "全部子 Agent 已委派完成，结束主编排。"
        if ctx.completed_step_types
        else "无需进一步委派。"
    )
    return ReActDecision(thought=summary, action="finish")


def rule_decide_agent(
    ctx: AgentRunContext,
    display_name: str,
    action_pipeline: list[str],
) -> ReActDecision:
    for action in action_pipeline:
        if action not in ctx.completed_actions:
            done = ", ".join(sorted(ctx.completed_actions)) or "无"
            brief = ctx.task_brief[:60] + ("…" if len(ctx.task_brief) > 60 else "")
            thought = (
                f"[{display_name}] 任务简报：{brief}。"
                f"已完成行动：{done}。下一步：{action}。"
            )
            return ReActDecision(thought=thought, action=action)
    return ReActDecision(thought="本 Agent 任务已全部完成。", action="finish")
