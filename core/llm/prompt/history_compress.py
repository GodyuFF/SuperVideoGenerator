"""超 context_window 时对较早对话做 LLM 摘要压缩。"""

from __future__ import annotations

from typing import Any

from core.conversation import ConversationStore
from core.llm.client import LLMClient
from core.llm.client.settings import LLMConfigManager
from core.llm.model.chat_message import ChatMessage, chat_message
from core.llm.model.llm_request import LlmRequest, ToolDefinition
from core.llm.prompt.chat_messages import (
    _message_summary_text,
    _with_summary_prefix,
    apply_snippet_chat_history,
    repair_tool_message_pairs,
    split_messages_for_compression,
)
from core.llm.prompt.loader import load_text
from core.llm.prompt.config import HISTORY_KEEP_MESSAGES
from core.llm.client.tokens import estimate_request_breakdown
from core.logging.setup import get_logger, log_stage

logger = get_logger("core.llm.prompt.history_compress")

_SUMMARY_SYSTEM = load_text("rules/history_summary.md") or (
    "将较早对话压缩为中文摘要，保留用户诉求、已确认设定与关键执行结果。"
)


def _message_line(msg: ChatMessage) -> str:
    """将单条消息格式化为 LLM 摘要输入行（含行动与观察）。"""
    role = str(msg.get("role", "user"))
    text = _message_summary_text(msg).strip()
    if not text:
        return ""
    return f"[{role}] {text}"


def _format_messages_block(messages: list[ChatMessage]) -> str:
    lines = [_message_line(m) for m in messages]
    return "\n\n".join(line for line in lines if line)


def _split_for_compression(
    messages: list[ChatMessage],
    *,
    keep: int,
    pin_first_user: bool,
) -> tuple[list[ChatMessage], list[ChatMessage]]:
    """按 ReAct 轮次切分，保留最近 keep 轮。"""
    return split_messages_for_compression(
        messages, keep=keep, pin_first_user=pin_first_user
    )


def estimate_request_over_window(
    *,
    system_prompt: str,
    tools: list[ToolDefinition] | None,
    messages: list[ChatMessage],
    config: LLMConfigManager,
) -> tuple[bool, Any]:
    """判断预估输入 token 是否超过配置的 context_window_tokens。"""
    settings = config.get_settings()
    req = LlmRequest(
        system=system_prompt,
        tools=list(tools or []),
        messages=list(messages),
    )
    breakdown = estimate_request_breakdown(req, settings.max_tokens)
    over = breakdown.prompt_estimated_tokens > settings.context_window_tokens
    return over, breakdown


async def maybe_compress_chat_history(
    client: LLMClient,
    config: LLMConfigManager,
    *,
    messages: list[ChatMessage],
    system_prompt: str,
    tools: list[ToolDefinition] | None = None,
    pin_first_user: bool = False,
    log_context: dict[str, Any] | None = None,
    conversations: ConversationStore | None = None,
    conversation_id: str = "",
    project_id: str = "",
    script_id: str = "",
    channel: str = "master",
    agent_name: str = "",
) -> list[ChatMessage]:
    """若预估 token 超 context_window，对 keep 条以外的消息做 LLM 摘要。"""
    if not messages:
        return []

    settings = config.get_settings()
    over, breakdown = estimate_request_over_window(
        system_prompt=system_prompt,
        tools=tools,
        messages=messages,
        config=config,
    )
    if not over:
        return list(messages)

    keep_n = max(1, int(settings.history_keep_messages or HISTORY_KEEP_MESSAGES))
    kept, older = _split_for_compression(
        messages, keep=keep_n, pin_first_user=pin_first_user
    )
    if not older:
        return apply_snippet_chat_history(messages, pin_first_user=pin_first_user)

    block = _format_messages_block(older)
    log_ctx = dict(log_context or {})
    log_stage(
        logger,
        "llm.history_compress",
        "对话超窗，LLM 摘要较早历史",
        prompt_estimated_tokens=breakdown.prompt_estimated_tokens,
        total_estimated_tokens=breakdown.total_estimated_tokens,
        window=settings.context_window_tokens,
        dropped=len(older),
    )

    summary_request = LlmRequest(
        system=_SUMMARY_SYSTEM,
        messages=[
            chat_message(
                "user",
                f"以下是需要摘要的较早对话（共 {len(older)} 条）：\n\n{block}",
            )
        ],
    )
    try:
        summary_text = await client.complete(
            summary_request,
            log_context={
                **log_ctx,
                "role": "history_compress",
                "response_kind": "history_summary",
            },
            summary_prefix="历史摘要",
            response_kind="history_summary",
        )
        summary_text = summary_text.strip()
    except Exception as e:
        log_stage(
            logger,
            "llm.history_compress",
            "LLM 摘要失败，回退 snippet 滑窗",
            error=str(e),
        )
        return apply_snippet_chat_history(messages, pin_first_user=pin_first_user)

    prefix = f"（较早对话 LLM 摘要）\n{summary_text}"
    result = repair_tool_message_pairs(_with_summary_prefix(kept, prefix))

    if conversations and conversation_id and summary_text:
        try:
            conversations.add_orphan_observation(
                conversation_id,
                project_id,
                script_id,
                prefix,
                channel=channel,  # type: ignore[arg-type]
                agent_name=agent_name,
            )
        except Exception:
            pass

    return result


async def prepare_react_chat_history(
    client: LLMClient,
    config: LLMConfigManager,
    *,
    messages: list[ChatMessage],
    system_prompt: str,
    tools: list[ToolDefinition] | None = None,
    pin_first_user: bool = False,
    log_context: dict[str, Any] | None = None,
    conversations: ConversationStore | None = None,
    conversation_id: str = "",
    project_id: str = "",
    script_id: str = "",
    channel: str = "master",
    agent_name: str = "",
) -> list[ChatMessage]:
    """统一 ReAct 历史压缩入口：仅当输入 token 超窗时 LLM 摘要，否则保留完整历史。"""
    if not messages:
        return []

    over, _ = estimate_request_over_window(
        system_prompt=system_prompt,
        tools=tools,
        messages=messages,
        config=config,
    )
    if over:
        compressed = await maybe_compress_chat_history(
            client,
            config,
            messages=messages,
            system_prompt=system_prompt,
            tools=tools,
            pin_first_user=pin_first_user,
            log_context=log_context,
            conversations=conversations,
            conversation_id=conversation_id,
            project_id=project_id,
            script_id=script_id,
            channel=channel,
            agent_name=agent_name,
        )
        return repair_tool_message_pairs(compressed)

    return repair_tool_message_pairs(list(messages))

