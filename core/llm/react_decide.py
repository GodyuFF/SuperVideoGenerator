"""统一 tool_calls ReAct 决策：主编排与子 Agent 共用。"""

from collections.abc import Callable
from typing import Any

from core.llm.agent.react_core import AgentRunContext, ReActDecision
from core.conversation import ConversationStore
from core.llm.client import LLMClient
from core.llm.protocol import parse_react_tool_calls
from core.llm.settings import LLMConfigManager
from core.llm.streaming import OnDelta
from core.execution.cancel import make_abort_checker
from core.llm.tools.shared.agent_tools import ASK_USER_QUESTION_ACTION
from core.llm.tools_schema import build_master_react_tools, build_sub_agent_react_tools
from core.llm.prompt.tools.registry import unique_actions
from core.logging.setup import get_logger, log_stage
from core.llm.model.chat_message import ChatMessage, chat_message
from core.llm.prompt.builder import (
    build_react_state_json,
    build_react_state_turn_content,
    build_react_static_system,
    build_react_system as _base_react_system,
    filter_available_actions,
)
from core.llm.prompt.loader import load_text
from core.models.entities import ExecutionMode
from core.llm.prompt.chat_messages import (
    MASTER_STATE_INSTRUCTIONS,
    SUB_AGENT_STATE_INSTRUCTIONS,
    build_agent_react_chat_history,
    build_llm_request,
    build_llm_request_ordered,
    master_channel_has_user,
    messages_to_chat_history,
)
from core.llm.prompt.history_compress import (
    finalize_react_chat_history,
    maybe_compress_chat_history,
)
from core.llm.model.plan_context import trim_plan_status_history
from core.llm.master.actions import pipeline_for_style
from core.llm.prompt.context_manager import AgentContextManager
from core.llm.prompt.context_window import prepare_master_context
from core.llm.prompt.project_context import format_project_context_header
from core.llm.model.llm_request import LlmRequest
from core.llm.tool_call_guard import (
    PLACEHOLDER_CORRECTION_USER,
    assert_not_placeholder_tool_call,
    format_placeholder_failure,
    is_placeholder_parse_error,
    is_placeholder_tool_call,
)
from core.store.memory import MemoryStore

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


def _finalize_react_decision(decision: ReActDecision, allowed_actions: list[str]) -> ReActDecision:
    try:
        decision.action = sanitize_action(decision.action, allowed_actions)
    except ValueError as e:
        raise RuntimeError(str(e)) from e
    return decision


def _resolve_react_tool_choice(
    config: LLMConfigManager | None,
) -> dict[str, str] | None:
    if config is None:
        return None
    from core.llm.client.tool_choice import resolve_react_tool_choice

    settings = config.get_settings()
    return resolve_react_tool_choice(
        settings.provider,
        config.resolved_model(),
        thinking_override=settings.thinking_mode,
    )


_EDITING_NEXT_HINTS: list[tuple[frozenset[str], frozenset[str], str]] = [
    (
        frozenset({"load_edit_context"}),
        frozenset({"plan_edit_timeline", "get_edit_timeline"}),
        "建议下一步：plan_edit_timeline（若 user_edited 可先 get_edit_timeline）。",
    ),
    (
        frozenset({"plan_edit_timeline", "get_edit_timeline"}),
        frozenset({"validate_edit_assets"}),
        "建议下一步：validate_edit_assets。",
    ),
    (
        frozenset({"validate_edit_assets"}),
        frozenset({"gather_media", "report_missing_assets"}),
        "建议下一步：gather_media 或 report_missing_assets。",
    ),
    (
        frozenset({"gather_media"}),
        frozenset({"compose_final"}),
        "建议下一步：compose_final。",
    ),
]


def _sub_agent_react_hint(agent_name: str, completed_list: list[str]) -> str:
    completed = ", ".join(completed_list) or "无"
    hint = (
        f"已完成：{completed}；"
        f"必须通过 tool_calls 从 available_actions 中选择下一行动。"
    )
    if agent_name != "editing_agent":
        return hint
    done = {x.strip() for x in completed_list if x and x.strip() not in ("无", "")}
    for need, exclude, suggestion in _EDITING_NEXT_HINTS:
        if need <= done and not exclude & done:
            return f"{hint}{suggestion}"
    return hint


def _request_with_placeholder_correction(request: LlmRequest) -> LlmRequest:
    messages = list(request.messages)
    messages.append(chat_message("user", PLACEHOLDER_CORRECTION_USER))
    return request.model_copy(update={"messages": messages})


def _should_retry_placeholder(result, exc: BaseException | None) -> bool:
    if is_placeholder_tool_call(result):
        return True
    if exc is not None and is_placeholder_parse_error(exc):
        return True
    return False


async def _complete_react_decision(
    client: LLMClient,
    request: LlmRequest,
    *,
    allowed_actions: list[str],
    log_context: dict[str, Any],
    summary_prefix: str,
    on_delta: OnDelta | None,
    should_abort: Callable[[], bool] | None = None,
) -> ReActDecision:
    """调用 LLM tool_calls 并解析；占位符 tool_call 时纠正重试一次。"""
    from core.llm.tool_call_guard import PlaceholderToolCallError

    agent_name = str(log_context.get("agent_name", ""))

    async def _call(req: LlmRequest):
        return await client.complete_tool_calls(
            req,
            log_context=log_context,
            summary_prefix=summary_prefix,
            on_delta=on_delta,
            should_abort=should_abort,
        )

    def _parse(result) -> ReActDecision:
        assert_not_placeholder_tool_call(result)
        decision = parse_react_tool_calls(result)
        return _finalize_react_decision(decision, allowed_actions)

    result = await _call(request)
    parse_error: BaseException | None = None
    try:
        return _parse(result)
    except (PlaceholderToolCallError, ValueError) as e:
        parse_error = e

    if not _should_retry_placeholder(result, parse_error):
        if parse_error:
            raise parse_error
        raise RuntimeError(format_placeholder_failure(result, agent_name=agent_name))

    log_stage(
        logger,
        "llm.react",
        "占位符 tool_call，纠正重试",
        agent=agent_name,
        tool=result.primary_name(),
    )
    retry_result = await _call(_request_with_placeholder_correction(request))
    try:
        return _parse(retry_result)
    except Exception as e:
        detail = format_placeholder_failure(
            retry_result,
            agent_name=agent_name,
            allowed_actions=allowed_actions,
        )
        raise RuntimeError(f"{detail}；重试后仍失败: {e}") from e


def build_master_react_state_json(session: Any, *, use_chat_history: bool = False) -> str:
    """主编排 ReAct 当前步动态状态（JSON 字符串，拼入 system）。"""
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
    extra["next_actions"] = session.next_actions()
    from core.llm.master.actions import ACTION_TO_STEP, STEP_META
    from core.llm.master.session import build_master_sub_agents

    extra["sub_agents"] = [
        {
            "delegate": spec.delegate_action,
            "step_type": spec.step_type,
            "title": spec.display_name,
            "depends_on": STEP_META.get(spec.step_type, {}).get("depends_on", ""),
            "produces": STEP_META.get(spec.step_type, {}).get("produces", ""),
            "completed": ACTION_TO_STEP.get(spec.delegate_action) in getattr(
                session, "completed_step_types", set()
            ),
        }
        for spec in build_master_sub_agents()
        if spec.delegate_action in pipeline_for_style(session.style_mode)
    ]
    if getattr(session, "execution_plan", None):
        extra["execution_plan"] = session.execution_plan
    history = trim_plan_status_history(getattr(session, "plan_status_history", []) or [])
    if history:
        extra["plan_status_history"] = history
    remaining = getattr(session, "last_remaining_plan", None) or []
    if remaining:
        extra["last_remaining_plan"] = remaining
    return build_react_state_json(
        task_brief=session.task_brief,
        available_actions=session.available_actions(),
        completed=session.completed_labels(),
        observations=observations,
        extra=extra,
        include_observations=include_observations,
    )


def build_react_system(role_prompt: str = "", *, goal_mode: bool = False) -> str:
    base = _base_react_system(role_prompt)
    if goal_mode:
        extra = load_text("rules/goal_mode.md")
        if extra:
            base = f"{base}\n\n{extra}"
    return base


def build_master_react_turn_user(session: Any, *, use_chat_history: bool = False) -> str:
    """主编排 ReAct 动态编排状态（拼入 messages 末条 user）。"""
    state = build_master_react_state_json(session, use_chat_history=use_chat_history)
    completed = session.completed_labels() or ["无"]
    next_acts = session.next_actions() or ["finish"]
    hint = (
        f"已完成：{', '.join(completed)}；"
        f"建议下一步：{', '.join(next_acts)}。"
        f"必须通过 tool_calls 调用 available_actions 中的函数。"
    )
    return build_react_state_turn_content(
        state,
        hint=hint,
        instructions=MASTER_STATE_INSTRUCTIONS,
    )


def build_master_react_system(session: Any, *, use_chat_history: bool = False) -> str:
    """兼容包装：静态 system + 状态块拼接（测试/日志用）。"""
    goal_mode = str(session.extra.get("execution_mode", "")) == ExecutionMode.GOAL.value
    static = build_react_static_system(session.agent.description, goal_mode=goal_mode)
    turn = build_master_react_turn_user(session, use_chat_history=use_chat_history)
    return f"{static.rstrip()}\n\n{turn}"


async def decide_react(
    client: LLMClient,
    config: LLMConfigManager | None,
    *,
    role_prompt: str = "",
    allowed_actions: list[str],
    agent_name: str,
    log_context: dict[str, Any],
    system_prompt: str | None = None,
    anchor_user: str | None = None,
    turn_user: str | None = None,
    on_delta: OnDelta | None = None,
    summary_prefix: str = "ReAct tool_calls",
    chat_history: list[ChatMessage] | None = None,
) -> ReActDecision:
    """子 Agent 单轮 ReAct LLM 决策（OpenAI tool_calls）。"""
    goal_mode = str((log_context or {}).get("execution_mode", "")) == ExecutionMode.GOAL.value
    sys = system_prompt or build_react_system(role_prompt, goal_mode=goal_mode)
    request = build_llm_request_ordered(
        system_prompt=sys,
        tools=build_sub_agent_react_tools(
            agent_name,
            allowed_actions,
            include_ask_user=ASK_USER_QUESTION_ACTION in allowed_actions,
        ),
        anchor_user=anchor_user,
        history=chat_history,
        turn_user=turn_user,
        tool_choice=_resolve_react_tool_choice(config),
    )
    try:
        script_id = str(log_context.get("script_id", ""))
        abort_checker = make_abort_checker(script_id) if script_id else None
        return await _complete_react_decision(
            client,
            request,
            allowed_actions=allowed_actions,
            log_context=log_context,
            summary_prefix=summary_prefix,
            on_delta=on_delta,
            should_abort=abort_checker,
        )
    except Exception as e:
        log_stage(
            logger,
            "llm.react",
            "ReAct LLM 失败",
            agent=log_context.get("agent_name", ""),
            error=str(e),
        )
        raise


async def decide_master_session(
    client: LLMClient,
    config: LLMConfigManager,
    session: Any,
    conversations: ConversationStore,
    on_delta: OnDelta | None = None,
) -> ReActDecision:
    """主编排 ReActSession 单轮决策（静态 system + 末条 user 编排状态）。"""
    require_llm(config)
    if not master_channel_has_user(conversations, session.conversation_id):
        raise RuntimeError("主编排决策失败：会话中无用户消息")

    raw_chat = messages_to_chat_history(
        conversations.list_messages(session.conversation_id, "master")
    )
    allowed = session.available_actions()
    prompt_actions = filter_available_actions(allowed, session.completed_labels())
    tools = build_master_react_tools(
        prompt_actions,
        include_ask_user=ASK_USER_QUESTION_ACTION in prompt_actions,
    )
    goal_mode = str(session.extra.get("execution_mode", "")) == ExecutionMode.GOAL.value
    static_system = build_react_static_system(
        session.agent.description, goal_mode=goal_mode
    )
    turn_user = build_master_react_turn_user(
        session, use_chat_history=bool(raw_chat)
    )
    estimate_prompt = f"{static_system.rstrip()}\n\n{turn_user}"
    log_ctx = {
        "project_id": session.project_id,
        "script_id": session.script_id,
        "conversation_id": session.conversation_id,
        "agent_name": session.agent_name,
        "role": "master",
        "iteration": session.iteration,
    }
    compressed = await maybe_compress_chat_history(
        client,
        config,
        messages=raw_chat,
        system_prompt=estimate_prompt,
        tools=tools,
        pin_first_user=True,
        log_context=log_ctx,
        conversations=conversations,
        conversation_id=session.conversation_id,
        project_id=session.project_id,
        script_id=session.script_id,
        channel="master",
    )
    chat_history = await finalize_react_chat_history(
        compressed, pin_first_user=True
    )
    request = build_llm_request(
        system_prompt=static_system,
        tools=tools,
        history=chat_history,
        turn_user=turn_user,
        tool_choice=_resolve_react_tool_choice(config),
    )
    try:
        abort_checker = make_abort_checker(session.script_id)
        return await _complete_react_decision(
            client,
            request,
            allowed_actions=prompt_actions,
            log_context=log_ctx,
            summary_prefix="ReAct tool_calls",
            on_delta=on_delta,
            should_abort=abort_checker,
        )
    except Exception as e:
        log_stage(
            logger,
            "llm.react",
            "ReAct LLM 失败",
            agent=session.agent_name,
            error=str(e),
        )
        raise


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
    store: MemoryStore | None = None,
) -> ReActDecision:
    """子 Agent 单轮 ReAct 决策。"""
    require_llm(config)
    available = unique_actions(
        list(action_pipeline)
        + list(ad_hoc_actions or [])
        + list(read_actions or [])
    )
    if "finish" not in available:
        available.append("finish")
    execution_mode = str(ctx.work_context.get("execution_mode", ""))
    if execution_mode == ExecutionMode.GOAL.value:
        available = [a for a in available if a != ASK_USER_QUESTION_ACTION]
    raw_chat = messages_to_chat_history(
        conversations.list_messages(ctx.conversation_id, "agent", ctx.agent_name),
        include_task=False,
    )
    react_inputs = AgentContextManager.sub_agent.build_react_inputs(
        ctx,
        role_prompt=role_prompt,
        display_name=display_name,
        available_actions=available,
        store=store,
    )
    prompt_actions = filter_available_actions(
        available, react_inputs["completed"]
    )
    extra = dict(react_inputs.get("extra") or {})
    if raw_chat:
        extra.pop("history_summary", None)
    state_json = build_react_state_json(
        task_brief=react_inputs["task_brief"],
        available_actions=react_inputs["available_actions"],
        completed=react_inputs["completed"],
        observations=react_inputs["observations"] if not raw_chat else None,
        extra=extra,
        include_observations=not bool(raw_chat),
    )
    completed_list = react_inputs["completed"] or ["无"]
    hint = _sub_agent_react_hint(ctx.agent_name, completed_list)
    static_system = build_react_static_system(
        role_prompt,
        goal_mode=execution_mode == ExecutionMode.GOAL.value,
    )
    turn_user = build_react_state_turn_content(
        state_json,
        hint=hint,
        instructions=SUB_AGENT_STATE_INSTRUCTIONS,
    )
    anchor_user = react_inputs["task_brief"]
    if store is not None:
        header = format_project_context_header(
            extra.get("project_context")
            or {}
        )
        if header:
            anchor_user = f"{header}\n\n{anchor_user}"
    log_ctx = {
        "project_id": ctx.work_context.get("project_id", ""),
        "script_id": ctx.script_id,
        "conversation_id": ctx.conversation_id,
        "agent_name": ctx.agent_name,
        "step_id": ctx.step_id,
        "role": "sub_agent",
        "iteration": ctx.iteration,
        "execution_mode": execution_mode,
    }
    tools = build_sub_agent_react_tools(
        ctx.agent_name,
        prompt_actions,
        include_ask_user=ASK_USER_QUESTION_ACTION in prompt_actions,
    )
    estimate_prompt = f"{static_system.rstrip()}\n\n{turn_user}"
    compressed = await maybe_compress_chat_history(
        client,
        config,
        messages=raw_chat,
        system_prompt=estimate_prompt,
        tools=tools,
        log_context=log_ctx,
        conversations=conversations,
        conversation_id=ctx.conversation_id,
        project_id=str(ctx.work_context.get("project_id", "")),
        script_id=ctx.script_id,
        channel="agent",
        agent_name=ctx.agent_name,
    )
    chat_history = await finalize_react_chat_history(compressed)
    return await decide_react(
        client,
        config,
        system_prompt=static_system,
        anchor_user=anchor_user,
        turn_user=turn_user,
        allowed_actions=prompt_actions,
        agent_name=ctx.agent_name,
        log_context=log_ctx,
        chat_history=chat_history or None,
    )
