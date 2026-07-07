"""ConversationMessage → Chat API 多轮消息映射与历史构建。"""

from typing import Any

from core.conversation import ConversationMessage, ConversationStore, MessageKind, MessageRole
from core.llm.model.chat_message import (
    ChatMessage,
    ContentBlock,
    canonical_to_anthropic_messages,
    chat_message,
    message_content_text,
    normalize_content,
    tool_message,
    wire_message_chars_anthropic,
)
from core.llm.model.llm_request import LlmRequest, ToolDefinition
from core.llm.prompt.config import (
    COMPRESSION_SNIPPET_CHARS,
    HISTORY_MAX_CHARS,
    HISTORY_WINDOW_SIZE,
)


def _message_flat_chars(msg: ChatMessage) -> str:
    wire = canonical_to_anthropic_messages([msg])
    if not wire:
        return ""
    return str(wire_message_chars_anthropic(wire[0]))


def conversation_messages_to_chat_blocks(
    messages: list[ConversationMessage],
    *,
    include_task: bool = True,
) -> list[ChatMessage]:
    """将四 Role 存储消息映射为 canonical Chat 消息（近透传）。"""
    result: list[ChatMessage] = []

    for msg in messages:
        if msg.message_kind == MessageKind.TASK_BRIEF and not include_task:
            continue

        if msg.role == MessageRole.USER:
            result.append(chat_message("user", msg.content))
            continue

        if msg.role == MessageRole.SYSTEM:
            result.append(chat_message("system", msg.content))
            continue

        if msg.role == MessageRole.ASSISTANT:
            result.append(chat_message("assistant", msg.content))
            continue

        if msg.role == MessageRole.TOOL:
            content = (
                msg.content
                if isinstance(msg.content, str)
                else message_content_text(msg.content)
            )
            result.append(tool_message(msg.tool_call_id, content))
            continue

    return result


def conversation_message_to_chat(msg: ConversationMessage) -> ChatMessage | None:
    """将单条隔离会话消息映射为 canonical Chat 消息（不合并相邻 THOUGHT+ACTION）。"""
    blocks = conversation_messages_to_chat_blocks([msg])
    return blocks[0] if blocks else None


def messages_to_chat_history(
    messages: list[ConversationMessage],
    *,
    include_task: bool = True,
) -> list[ChatMessage]:
    """批量转换会话消息为 canonical Chat 历史。"""
    return conversation_messages_to_chat_blocks(messages, include_task=include_task)


def fit_chat_history(
    messages: list[ChatMessage],
    *,
    window_size: int = HISTORY_WINDOW_SIZE,
    max_chars: int = HISTORY_MAX_CHARS,
    pin_first_user: bool = False,
) -> tuple[list[ChatMessage], str]:
    """对 Chat 历史做滑窗与字符预算压缩，返回 (保留消息, 摘要)。"""
    if not messages:
        return [], ""

    pinned: ChatMessage | None = None
    pool = list(messages)
    if pin_first_user and pool and pool[0].get("role") == "user":
        pinned = pool.pop(0)

    dropped_by_window = max(0, len(pool) - window_size)
    windowed = pool[-window_size:] if window_size > 0 else list(pool)

    kept: list[ChatMessage] = []
    total = 0
    compressed_in_window = 0
    for msg in reversed(windowed):
        content = _message_flat_chars(msg).strip()
        if not content:
            continue
        add = len(content) + 8
        if kept and total + add > max_chars:
            compressed_in_window += 1
            continue
        kept.insert(0, msg)
        total += add

    if not kept and pool:
        last = pool[-1]
        flat = _message_flat_chars(last)
        kept = [
            chat_message(
                str(last.get("role", "user")),
                flat[:max_chars],
            )
        ]

    dropped_count = dropped_by_window + compressed_in_window
    summary = ""
    if dropped_count > 0:
        dropped_msgs = pool[: len(pool) - len(kept)]
        snippets = [
            f"- [{m.get('role', 'user')}] {_truncate(_message_flat_chars(m), COMPRESSION_SNIPPET_CHARS)}"
            for m in dropped_msgs
            if _message_flat_chars(m).strip()
        ]
        if snippets:
            summary = (
                f"（已压缩较早的 {dropped_count} 条对话，以下为摘要）\n"
                + "\n".join(snippets)
            )

    if pinned is not None:
        kept = [pinned] + kept

    return kept, summary


def _truncate(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _with_summary_prefix(
    history: list[ChatMessage], summary: str
) -> list[ChatMessage]:
    if not summary.strip():
        return history
    return [chat_message("assistant", summary.strip())] + history


MASTER_STATE_HEADER = "## 当前编排状态"
REACT_STATE_HEADER = MASTER_STATE_HEADER

MASTER_STATE_INSTRUCTIONS = """说明（每轮决策前必读）：
1. **必须通过 tool_calls 调用且只能调用**下方 JSON 的 `available_actions` 中提供的 function；角色说明中的行动全集仅供参考。
2. `completed_actions` 与 `available_actions` 使用相同的 action 名称（如 `delegate_script_design`）；已完成的一次性 delegate 不会出现在 `available_actions` 中。
3. 当必要步骤均已完成、available_actions 仅剩 `finish` 时，应选择 `finish`。
4. 勿根据对话历史中曾出现的行动，选用当前 available_actions 中已不存在的 action。
5. 若最近 observation 报告图片生成失败且建议修订提示词，`delegate_script_design` 可能已重新开放，应先分析失败明细再决定是否委派 script_agent 修 prompt。
6. **新对话重新规划**：`completed_actions` 仅记录**本对话**已成功委派的步骤；`pipeline_progress.inferred_completed_steps` 仅为 Store 素材快照，**不得**当作本对话已完成。据 `user_message` 与 `next_actions` 选择下一步；用户要求从剪辑/合成继续且 `ready_for_edit_compose=true` 时，优先 `delegate_edit_compose`，勿机械重跑 script_design。"""

SUB_AGENT_STATE_INSTRUCTIONS = """说明（每轮决策前必读）：
1. **必须通过 tool_calls 调用且只能调用**下方 JSON 的 `available_actions` 中提供的 function。
2. `completed_actions` 记录已成功执行过的行动；**一次性步骤**（如 `parse_brief`）完成后不会出现在 `available_actions` 中；**可重复步骤**（如 `create_plot`、`create_character`、`update_*`、`list_text_assets`）仍可多次选用。
3. 当本子 Agent 流水线任务已完成时，应选择 `finish` 交还主编排。
4. `plan_slice` / `project_context` 由系统注入，勿重复编造已完成步骤。"""

ACTION_CONTEXT_HEADER = "## 当前行动上下文"


def _append_history_messages(
    messages: list[ChatMessage],
    history: list[ChatMessage] | None,
) -> None:
    if not history:
        return
    for msg in history:
        role = str(msg.get("role", "")).strip()
        if role == "system":
            continue
        entry: ChatMessage = {
            "role": role,
            "content": normalize_content(msg.get("content")),
        }
        if msg.get("tool_call_id"):
            entry["tool_call_id"] = str(msg["tool_call_id"])
        messages.append(entry)


def build_llm_request_ordered(
    *,
    system_prompt: str,
    tools: list[ToolDefinition] | None = None,
    anchor_user: str | list[ContentBlock] | None = None,
    history: list[ChatMessage] | None = None,
    turn_user: str | list[ContentBlock] | None = None,
    tool_choice: dict[str, Any] | None = None,
) -> LlmRequest:
    """
    按时间序组装 messages：锚点 user（任务/创意）→ ReAct 历史。

    - anchor_user → 首条 user（任务简报 / 用户创意）
    - history → 中间 assistant / tool 轮次
    - turn_user → 末条 user（ReAct 编排状态 JSON / 行动上下文）
    """
    messages: list[ChatMessage] = []
    if anchor_user is not None:
        anchor_text = (
            anchor_user.strip()
            if isinstance(anchor_user, str)
            else message_content_text(anchor_user)
        )
        if anchor_text:
            messages.append(chat_message("user", anchor_user))
    _append_history_messages(messages, history)
    if turn_user is not None:
        messages.append(chat_message("user", turn_user))
    if not messages:
        raise ValueError("需要 anchor_user、turn_user 或 history")
    return LlmRequest(
        system=system_prompt,
        tools=list(tools or []),
        messages=messages,
        tool_choice=tool_choice,
    )


def build_llm_request(
    *,
    system_prompt: str,
    tools: list[ToolDefinition] | None = None,
    history: list[ChatMessage] | None = None,
    turn_user: str | list[ContentBlock] | None = None,
    tool_choice: dict[str, Any] | None = None,
) -> LlmRequest:
    """
    组装 canonical LlmRequest：system / tools / messages 同级。

    - system_prompt → system 字段（不在 messages 内）
    - history → messages 中的 user/assistant
    - turn_user → 可选末条 user
    """
    return build_llm_request_ordered(
        system_prompt=system_prompt,
        tools=tools,
        history=history,
        turn_user=turn_user,
        tool_choice=tool_choice,
    )


def build_llm_messages(
    *,
    system_prompt: str,
    history: list[ChatMessage] | None = None,
    turn_user: str | list[ContentBlock] | None = None,
) -> list[ChatMessage]:
    """兼容包装：返回含 system 的 messages 列表（测试/旧调用方）。"""
    req = build_llm_request(
        system_prompt=system_prompt,
        history=history,
        turn_user=turn_user,
    )
    return [chat_message("system", req.system), *req.messages]


def last_user_content(source: LlmRequest | list[ChatMessage]) -> str:
    """从 LlmRequest 或 messages 中取末条 user 的文本内容。"""
    messages = source.messages if isinstance(source, LlmRequest) else source
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return message_content_text(msg.get("content", ""))
    return ""


def _parse_state_json_block(content: str) -> dict[str, Any] | None:
    """从含 REACT_STATE_HEADER 的文本块解析 JSON。"""
    from core.llm.json_parse import parse_llm_json_object

    if REACT_STATE_HEADER not in content:
        return None
    tail = content.split(REACT_STATE_HEADER, 1)[1].strip()
    for marker in (MASTER_STATE_INSTRUCTIONS, SUB_AGENT_STATE_INSTRUCTIONS):
        if marker in tail:
            tail = tail.split(marker, 1)[0].strip()
            break
    start = tail.find("{")
    if start < 0:
        return None
    try:
        return parse_llm_json_object(tail[start:])
    except ValueError:
        return None


def extract_react_state_json(source: LlmRequest | list[ChatMessage]) -> dict[str, Any] | None:
    """解析「当前编排状态」JSON：优先末条 user，回退 system（主编排与子 Agent 共用）。"""
    if isinstance(source, LlmRequest):
        last_user = last_user_content(source)
        if last_user:
            parsed = _parse_state_json_block(last_user)
            if parsed is not None:
                return parsed
        return _parse_state_json_block(source.system)
    if messages := source:
        last_user = last_user_content(messages)
        if last_user:
            parsed = _parse_state_json_block(last_user)
            if parsed is not None:
                return parsed
        if messages[0].get("role") == "system":
            return _parse_state_json_block(
                message_content_text(messages[0].get("content", ""))
            )
    return None


def extract_master_state_json(source: LlmRequest | list[ChatMessage]) -> dict[str, Any] | None:
    """兼容别名：同 extract_react_state_json。"""
    return extract_react_state_json(source)


def master_channel_has_user(
    conversations: ConversationStore,
    conversation_id: str,
) -> bool:
    """master 通道是否已有用户消息（主编排决策前置条件）。"""
    msgs = conversations.list_messages(conversation_id, "master")
    return any(m.role == MessageRole.USER for m in msgs)


def build_master_react_chat_history(
    conversations: ConversationStore,
    conversation_id: str,
) -> list[ChatMessage]:
    """主编排 ReAct：从 master 通道构建多轮 Chat 历史。"""
    msgs = conversations.list_messages(conversation_id, "master")
    chat = messages_to_chat_history(msgs)
    fitted, summary = fit_chat_history(chat, pin_first_user=True)
    return _with_summary_prefix(fitted, summary)


def build_agent_react_chat_history(
    conversations: ConversationStore,
    conversation_id: str,
    agent_name: str,
) -> list[ChatMessage]:
    """子 Agent ReAct / 行动：从 agent 通道构建多轮 Chat 历史（不含 TASK，任务由 anchor_user 注入）。"""
    msgs = conversations.list_messages(conversation_id, "agent", agent_name)
    chat = messages_to_chat_history(msgs, include_task=False)
    fitted, summary = fit_chat_history(chat)
    return _with_summary_prefix(fitted, summary)
