"""统一 JSON ReAct 决策：主编排与子 Agent 共用。"""

from typing import Any

from core.agents.react_core import AgentRunContext, ReActDecision
from core.conversation import ConversationStore
from core.llm.client import LLMClient
from core.llm.protocol import parse_react_json
from core.llm.settings import LLMConfigManager
from core.llm.streaming import OnDelta
from core.logging.setup import get_logger, log_stage
from core.prompt.builder import build_react_json_user, build_react_system
from core.prompt.chat_messages import (
    build_agent_react_chat_history,
    build_master_react_chat_history,
)
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
    chat_messages: list[dict[str, str]] | None = None,
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
            chat_messages=chat_messages,
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


def build_master_context_json(session: Any, *, use_chat_history: bool = False) -> str:
    """主编排 ReAct 动态 user 上下文（JSON）。"""
    extra = dict(session.extra or {})
    if use_chat_history:
        extra.pop("history_summary", None)
        prepared = prepare_master_context([])
        observations = None
        include_observations = False
    else:
        prepared = prepare_master_context(session.observations)
        if prepared.history_summary:
            extra["history_summary"] = prepared.history_summary
        observations = prepared.observations
        include_observations = True
    return build_react_json_user(
        task_brief=session.task_brief,
        available_actions=session.available_actions(),
        completed=session.completed_labels(),
        observations=observations,
        extra=extra,
        include_observations=include_observations,
    )


async def decide_master_session(
    client: LLMClient,
    config: LLMConfigManager,
    session: Any,
    conversations: ConversationStore,
    on_delta: OnDelta | None = None,
) -> ReActDecision:
    """主编排 ReActSession 单轮决策。"""
    require_llm(config)
    chat_messages = build_master_react_chat_history(
        conversations, session.conversation_id
    )
    context_json = build_master_context_json(session, use_chat_history=bool(chat_messages))
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
        chat_messages=chat_messages or None,
    )


async def decide_sub_agent(
    client: LLMClient,
    config: LLMConfigManager,
    ctx: AgentRunContext,
    *,
    conversations: ConversationStore,
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
    chat_messages = build_agent_react_chat_history(
        conversations, ctx.conversation_id, ctx.agent_name
    )
    react_inputs = AgentContextManager.sub_agent.build_react_inputs(
        ctx,
        role_prompt=role_prompt,
        display_name=display_name,
        available_actions=available,
    )
    extra = dict(react_inputs.get("extra") or {})
    if chat_messages:
        extra.pop("history_summary", None)
    context_json = build_react_json_user(
        task_brief=react_inputs["task_brief"],
        available_actions=react_inputs["available_actions"],
        completed=react_inputs["completed"],
        observations=react_inputs["observations"] if not chat_messages else None,
        extra=extra,
        include_observations=not bool(chat_messages),
    )
    log_ctx = {
        "project_id": ctx.work_context.get("project_id", ""),
        "script_id": ctx.script_id,
        "conversation_id": ctx.conversation_id,
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
        chat_messages=chat_messages or None,
    )
