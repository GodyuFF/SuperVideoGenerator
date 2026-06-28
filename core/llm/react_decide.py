"""统一 JSON ReAct 决策：主编排与子 Agent 共用。"""

from typing import Any

from core.agents.react_core import AgentRunContext, ReActDecision
from core.llm.client import LLMClient
from core.llm.protocol import parse_react_json
from core.llm.settings import LLMConfigManager
from core.llm.streaming import OnDelta
from core.logging.setup import get_logger, log_stage
from core.prompt.builder import build_react_json_user, build_react_system
from core.prompt.context_manager import AgentContextManager
from core.prompt.context_window import prepare_master_context

logger = get_logger("core.llm.react_decide")


def require_llm(config: LLMConfigManager) -> None:
    if not config.is_llm_available():
        raise RuntimeError(
            "未配置 API Key 或已关闭 LLM ReAct，请在 AI 配置中填写 Key 并启用 LLM ReAct"
        )


def sanitize_action(action: str, allowed: list[str]) -> str:
    action = action.strip()
    if action in allowed:
        return action
    for candidate in allowed:
        if candidate.lower() == action.lower():
            return candidate
    raise ValueError(f"非法 action「{action}」，允许: {allowed}")


async def decide_react(
    client: LLMClient,
    *,
    role_prompt: str,
    context_json: str,
    allowed_actions: list[str],
    log_context: dict[str, Any],
    on_delta: OnDelta | None = None,
    summary_prefix: str = "ReAct JSON",
) -> ReActDecision:
    """单轮 ReAct LLM 决策（JSON 协议）。"""
    try:
        raw = await client.complete_json(
            build_react_system(role_prompt),
            context_json,
            log_context=log_context,
            summary_prefix=summary_prefix,
            response_format={"type": "json_object"},
            on_delta=on_delta,
        )
        decision = parse_react_json(raw)
        try:
            decision.action = sanitize_action(decision.action, allowed_actions)
        except ValueError as e:
            raise RuntimeError(str(e)) from e
        return decision
    except Exception as e:
        log_stage(
            logger,
            "llm.react",
            "ReAct LLM 失败",
            agent=log_context.get("agent_name", ""),
            error=str(e),
        )
        raise


def build_master_context_json(session: Any) -> str:
    """主编排 ReAct 动态 user 上下文（JSON）。"""
    prepared = prepare_master_context(session.observations)
    extra = dict(session.extra or {})
    if prepared.history_summary:
        extra["history_summary"] = prepared.history_summary
    return build_react_json_user(
        task_brief=session.task_brief,
        available_actions=session.available_actions(),
        completed=session.completed_labels(),
        observations=prepared.observations,
        extra=extra,
    )


async def decide_master_session(
    client: LLMClient,
    config: LLMConfigManager,
    session: Any,
    on_delta: OnDelta | None = None,
) -> ReActDecision:
    """主编排 ReActSession 单轮决策。"""
    require_llm(config)
    context_json = build_master_context_json(session)
    log_ctx = {
        "project_id": session.project_id,
        "script_id": session.script_id,
        "conversation_id": session.conversation_id,
        "agent_name": session.agent_name,
        "role": "master",
        "iteration": session.iteration,
    }
    return await decide_react(
        client,
        role_prompt=session.agent.description,
        context_json=context_json,
        allowed_actions=session.available_actions(),
        log_context=log_ctx,
        on_delta=on_delta,
    )


async def decide_sub_agent(
    client: LLMClient,
    config: LLMConfigManager,
    ctx: AgentRunContext,
    *,
    display_name: str,
    role_prompt: str,
    action_pipeline: list[str],
    read_actions: list[str] | None = None,
    ad_hoc_actions: list[str] | None = None,
) -> ReActDecision:
    """子 Agent 单轮 ReAct 决策。"""
    require_llm(config)
    available = (
        list(action_pipeline)
        + list(ad_hoc_actions or [])
        + list(read_actions or [])
        + ["finish"]
    )
    react_inputs = AgentContextManager.sub_agent.build_react_inputs(
        ctx,
        role_prompt=role_prompt,
        display_name=display_name,
        available_actions=available,
    )
    context_json = build_react_json_user(**react_inputs)
    log_ctx = {
        "project_id": ctx.work_context.get("project_id", ""),
        "script_id": ctx.script_id,
        "agent_name": ctx.agent_name,
        "step_id": ctx.step_id,
        "role": "sub_agent",
        "iteration": ctx.iteration,
    }
    return await decide_react(
        client,
        role_prompt=role_prompt,
        context_json=context_json,
        allowed_actions=available,
        log_context=log_ctx,
    )
