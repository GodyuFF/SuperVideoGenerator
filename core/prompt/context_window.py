"""Agent 执行前历史上下文聚合、滑窗与压缩。"""

from dataclasses import dataclass

from core.conversation import ConversationMessage, ConversationRole, ConversationStore
from core.agents.react_core import AgentRunContext
from core.prompt.config import (
    COMPRESSION_SNIPPET_CHARS,
    HISTORY_MAX_CHARS,
    HISTORY_WINDOW_SIZE,
    OBSERVATION_MAX_CHARS,
    OBSERVATION_WINDOW_SIZE,
)


@dataclass
class PreparedContext:
    """送入 LLM 的压缩后上下文。"""

    observations: list[str]
    history_summary: str = ""
    dropped_observation_count: int = 0
    dropped_history_count: int = 0


def _truncate(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _fit_char_budget(items: list[str], max_chars: int) -> list[str]:
    """从尾部保留条目，使总字符不超过预算。"""
    if not items:
        return []
    kept: list[str] = []
    total = 0
    for item in reversed(items):
        part = item.strip()
        if not part:
            continue
        add = len(part) + (1 if kept else 0)
        if kept and total + add > max_chars:
            break
        kept.insert(0, part)
        total += add
    return kept or [_truncate(items[-1], max_chars)]


def _compress_items(
    items: list[str],
    *,
    window_size: int,
    max_chars: int,
    label: str,
) -> tuple[list[str], str, int]:
    """滑窗保留最近条目，较早条目压缩为摘要。"""
    if not items:
        return [], "", 0

    dropped_count = max(0, len(items) - window_size)
    windowed = items[-window_size:] if window_size > 0 else list(items)
    recent = _fit_char_budget(windowed, max_chars)

    summary = ""
    if dropped_count > 0:
        dropped = items[:dropped_count]
        snippets = [
            f"- [{label}{i + 1}] {_truncate(t, COMPRESSION_SNIPPET_CHARS)}"
            for i, t in enumerate(dropped)
            if t.strip()
        ]
        if snippets:
            summary = (
                f"（已压缩较早的 {dropped_count} 条{label}，以下为摘要）\n"
                + "\n".join(snippets)
            )

    return recent, summary, dropped_count


def conversation_to_history_lines(messages: list[ConversationMessage]) -> list[str]:
    """将隔离会话消息转为可送入 LLM 的历史行。"""
    lines: list[str] = []
    for msg in messages:
        if msg.role == ConversationRole.TASK:
            lines.append(f"[任务简报] {msg.content}")
        elif msg.role == ConversationRole.THOUGHT:
            lines.append(f"[思考] {msg.content}")
        elif msg.role == ConversationRole.ACTION:
            lines.append(f"[行动] {msg.content}")
        elif msg.role == ConversationRole.OBSERVATION:
            lines.append(f"[观察] {msg.content}")
    return lines


def prepare_observation_window(
    observations: list[str],
    *,
    window_size: int = OBSERVATION_WINDOW_SIZE,
    max_chars: int = OBSERVATION_MAX_CHARS,
) -> tuple[list[str], str, int]:
    return _compress_items(
        observations,
        window_size=window_size,
        max_chars=max_chars,
        label="观察",
    )


def prepare_sub_agent_context(
    ctx: AgentRunContext,
    conversations: ConversationStore,
) -> PreparedContext:
    """子 Agent 执行前：聚合会话历史 + observation，滑窗并压缩。"""
    messages = conversations.list_messages(ctx.script_id, "agent", ctx.agent_name)
    all_lines = conversation_to_history_lines(messages)
    # 思考/行动/任务简报进入 history_summary；观察走 observations 块，避免重复
    history_lines = [line for line in all_lines if not line.startswith("[观察]")]

    obs_recent, obs_summary, obs_dropped = prepare_observation_window(ctx.observations)
    _, hist_summary, hist_dropped = _compress_items(
        history_lines,
        window_size=HISTORY_WINDOW_SIZE,
        max_chars=HISTORY_MAX_CHARS,
        label="历史",
    )

    summaries = [s for s in (hist_summary, obs_summary) if s]
    combined_summary = "\n\n".join(summaries)

    return PreparedContext(
        observations=obs_recent,
        history_summary=combined_summary,
        dropped_observation_count=obs_dropped,
        dropped_history_count=hist_dropped,
    )


def prepare_master_context(
    observations: list[str],
) -> PreparedContext:
    """主编排 ReAct 执行前压缩 observation。"""
    recent, summary, dropped = prepare_observation_window(observations)
    return PreparedContext(
        observations=recent,
        history_summary=summary,
        dropped_observation_count=dropped,
    )
