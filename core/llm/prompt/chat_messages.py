"""ConversationMessage → Chat API 多轮消息映射与历史构建。"""

import json
from typing import Any

from core.conversation import ConversationMessage, ConversationStore, MessageKind, MessageRole
from core.llm.model.chat_message import (
    ChatMessage,
    ContentBlock,
    canonical_to_anthropic_messages,
    chat_message,
    flatten_content_blocks,
    message_content_text,
    normalize_content,
    text_block,
    tool_message,
    wire_message_chars_anthropic,
)
from core.llm.model.llm_request import LlmRequest, ToolDefinition
from core.llm.prompt.config import (
    COMPRESSION_SNIPPET_ASSISTANT_CHARS,
    COMPRESSION_SNIPPET_CHARS,
    COMPRESSION_SNIPPET_TOOL_CHARS,
    HISTORY_MAX_CHARS,
    HISTORY_WINDOW_SIZE,
)


def _message_wire_char_count(msg: ChatMessage) -> int:
    """估算单条消息 Anthropic wire 字符数（滑窗预算用）。"""
    wire = canonical_to_anthropic_messages([msg])
    if not wire:
        return 0
    return wire_message_chars_anthropic(wire[0])


def _message_summary_text(msg: ChatMessage) -> str:
    """将单条消息压平为可读文本（压缩摘要与 LLM 摘要输入用）。"""
    role = str(msg.get("role", "user"))
    blocks = normalize_content(msg.get("content"))
    flat = flatten_content_blocks(blocks).strip()
    if role == "tool" and flat and not flat.startswith("[观察]"):
        return f"[观察] {flat}"
    return flat


def _is_state_json_text(text: str) -> bool:
    """判断是否为编排状态 JSON 块（已在末条 user 注入，摘要时去重）。"""
    return MASTER_STATE_HEADER in text or ACTION_CONTEXT_HEADER in text


def _state_json_user_message(text: str) -> str:
    """从状态 JSON 块中提取 user_message 字段（若有）。"""
    parsed = _parse_state_json_block(text)
    if not parsed:
        return ""
    user_msg = str(parsed.get("user_message", "")).strip()
    return user_msg


def _tool_observation_keywords(text: str) -> str:
    """从观察文本中提取失败/成功等关键词行。"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    headline = lines[0]
    tags: list[str] = []
    lower = text.lower()
    if "failure_analysis" in lower or "【失败明细" in text:
        tags.append("失败明细")
    if "error" in lower or "失败" in text:
        tags.append("失败")
    if "已完成" in text or "已生成" in text or "已委派" in text:
        tags.append("成功")
    if tags:
        return f"{headline}（{'、'.join(tags[:3])}）"
    return headline


def _extractive_snippet(msg: ChatMessage) -> str:
    """从单条消息抽取高信息密度摘要片段。"""
    role = str(msg.get("role", "user"))
    summary = _message_summary_text(msg)
    if not summary.strip():
        return ""

    if _is_state_json_text(summary):
        user_msg = _state_json_user_message(summary)
        if user_msg:
            return _truncate(user_msg, COMPRESSION_SNIPPET_CHARS)
        return ""

    if role == "tool":
        return _truncate(
            _tool_observation_keywords(summary),
            COMPRESSION_SNIPPET_TOOL_CHARS,
        )

    if role == "assistant":
        blocks = normalize_content(msg.get("content"))
        for block in blocks:
            if block.get("type") != "tool_use":
                continue
            name = str(block.get("name", "")).strip()
            inp = block.get("input", {})
            obs_hint = ""
            if isinstance(inp, dict):
                obs_hint = str(inp.get("observation", "")).strip()[:60]
            snippet = f"[行动] {name}"
            if obs_hint:
                snippet += f": {obs_hint}"
            return _truncate(snippet, COMPRESSION_SNIPPET_ASSISTANT_CHARS)

    return _truncate(summary, COMPRESSION_SNIPPET_CHARS)


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


def _collect_tool_use_ids(msg: ChatMessage) -> set[str]:
    """从 assistant 消息中收集 tool_use block 的 id。"""
    if str(msg.get("role", "")) != "assistant":
        return set()
    ids: set[str] = set()
    for block in normalize_content(msg.get("content")):
        if block.get("type") == "tool_use":
            tool_id = str(block.get("id", "")).strip()
            if tool_id:
                ids.add(tool_id)
    return ids


def group_react_turns(messages: list[ChatMessage]) -> list[list[ChatMessage]]:
    """将消息分组为不可拆分的 ReAct 轮次（assistant+tool 成对）。"""
    turns: list[list[ChatMessage]] = []
    index = 0
    while index < len(messages):
        msg = messages[index]
        role = str(msg.get("role", "user"))
        if role == "assistant":
            tool_ids = _collect_tool_use_ids(msg)
            if tool_ids:
                turn = [msg]
                index += 1
                pending = set(tool_ids)
                while index < len(messages) and pending:
                    nxt = messages[index]
                    if str(nxt.get("role", "")) != "tool":
                        break
                    tool_call_id = str(nxt.get("tool_call_id", "")).strip()
                    if tool_call_id not in pending:
                        break
                    turn.append(nxt)
                    pending.discard(tool_call_id)
                    index += 1
                turns.append(turn)
                continue
        turns.append([msg])
        index += 1
    return turns


def _flatten_turns(turns: list[list[ChatMessage]]) -> list[ChatMessage]:
    """将轮次列表展平为消息序列。"""
    flat: list[ChatMessage] = []
    for turn in turns:
        flat.extend(turn)
    return flat


def _turn_wire_char_count(turn: list[ChatMessage]) -> int:
    """估算单轮消息 Anthropic wire 字符数。"""
    return sum(_message_wire_char_count(msg) for msg in turn) + 8 * len(turn)


def _flatten_tool_use_block(block: ContentBlock) -> str:
    """将 tool_use block 展平为可读行动文本。"""
    name = str(block.get("name", "")).strip()
    inp = block.get("input", {})
    if isinstance(inp, str):
        input_str = inp
    else:
        input_str = json.dumps(inp, ensure_ascii=False)
    return f"[行动] {name}: {input_str}" if name else f"[行动] {input_str}"


def _repair_user_blocks(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """将 user 内嵌 tool_result / tool_use 展平为文本 block。"""
    repaired: list[ContentBlock] = []
    for block in blocks:
        btype = block.get("type")
        if btype == "tool_result":
            content = str(block.get("content", "")).strip()
            if content:
                obs = content if content.startswith("[观察]") else f"[观察] {content}"
                repaired.append(text_block(obs))
            continue
        if btype == "tool_use":
            repaired.append(text_block(_flatten_tool_use_block(block)))
            continue
        repaired.append(block)
    return repaired


def _repair_assistant_blocks(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """将 assistant 内 orphan tool_use / tool_result 展平为文本 block。"""
    repaired: list[ContentBlock] = []
    for block in blocks:
        btype = block.get("type")
        if btype == "tool_use":
            repaired.append(text_block(_flatten_tool_use_block(block)))
            continue
        if btype == "tool_result":
            content = str(block.get("content", "")).strip()
            if content:
                obs = content if content.startswith("[观察]") else f"[观察] {content}"
                repaired.append(text_block(obs))
            continue
        repaired.append(block)
    return repaired


def _tool_to_observation_assistant(msg: ChatMessage) -> ChatMessage:
    """将孤立 tool 消息转为 assistant 观察文本。"""
    text = _message_summary_text(msg).strip()
    if text and not text.startswith("[观察]"):
        text = f"[观察] {text}"
    return chat_message("assistant", text or "[观察]")


def repair_tool_message_pairs(messages: list[ChatMessage]) -> list[ChatMessage]:
    """修复压缩后孤立的 tool / tool_use，避免 wire 层 invalid_request_error。"""
    if not messages:
        return []

    repaired: list[ChatMessage] = []
    for turn in group_react_turns(messages):
        if len(turn) == 1:
            msg = turn[0]
            role = str(msg.get("role", "user"))
            if role == "tool":
                repaired.append(_tool_to_observation_assistant(msg))
                continue
            if role == "user":
                blocks = normalize_content(msg.get("content"))
                if any(b.get("type") in ("tool_result", "tool_use") for b in blocks):
                    repaired.append(chat_message("user", _repair_user_blocks(blocks)))
                else:
                    repaired.append(msg)
                continue
            if role == "assistant":
                blocks = normalize_content(msg.get("content"))
                has_tool_use = any(b.get("type") == "tool_use" for b in blocks)
                has_tool_result = any(b.get("type") == "tool_result" for b in blocks)
                if has_tool_use or has_tool_result:
                    repaired.append(chat_message("assistant", _repair_assistant_blocks(blocks)))
                else:
                    repaired.append(msg)
                continue
            repaired.append(msg)
            continue

        assistant_msg = turn[0]
        tool_msgs = turn[1:]
        paired_ids = {
            str(tool_msg.get("tool_call_id", "")).strip()
            for tool_msg in tool_msgs
            if str(tool_msg.get("tool_call_id", "")).strip()
        }
        blocks = normalize_content(assistant_msg.get("content"))
        kept_blocks: list[ContentBlock] = []
        for block in blocks:
            btype = block.get("type")
            if btype == "tool_result":
                content = str(block.get("content", "")).strip()
                if content:
                    obs = content if content.startswith("[观察]") else f"[观察] {content}"
                    kept_blocks.append(text_block(obs))
                continue
            if btype == "tool_use":
                tool_id = str(block.get("id", "")).strip()
                if tool_id and tool_id in paired_ids:
                    kept_blocks.append(block)
                else:
                    kept_blocks.append(text_block(_flatten_tool_use_block(block)))
                continue
            kept_blocks.append(block)
        repaired.append(chat_message("assistant", kept_blocks))
        repaired.extend(tool_msgs)

    return repaired


def split_messages_for_compression(
    messages: list[ChatMessage],
    *,
    keep: int,
    pin_first_user: bool,
) -> tuple[list[ChatMessage], list[ChatMessage]]:
    """按 ReAct 轮次切分消息，保留最近 keep 轮用于压缩。"""
    if not messages or keep <= 0:
        return list(messages), []

    pinned: ChatMessage | None = None
    pool = list(messages)
    if pin_first_user and pool and pool[0].get("role") == "user":
        pinned = pool.pop(0)

    turns = group_react_turns(pool)
    if len(turns) <= keep:
        kept = ([pinned] if pinned else []) + _flatten_turns(turns)
        return kept, []

    older_turns = turns[: len(turns) - keep]
    recent_turns = turns[-keep:]
    kept = ([pinned] if pinned else []) + _flatten_turns(recent_turns)
    older = _flatten_turns(older_turns)
    return kept, older


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

    all_turns = group_react_turns(pool)
    windowed_turns: list[list[ChatMessage]] = []
    msg_count = 0
    if window_size > 0:
        for turn in reversed(all_turns):
            turn_len = len(turn)
            if windowed_turns and msg_count + turn_len > window_size:
                break
            windowed_turns.insert(0, turn)
            msg_count += turn_len
    else:
        windowed_turns = list(all_turns)

    dropped_by_window = len(pool) - sum(len(turn) for turn in windowed_turns)

    kept_turns: list[list[ChatMessage]] = []
    total = 0
    compressed_in_window = 0
    for turn in reversed(windowed_turns):
        turn_chars = _turn_wire_char_count(turn)
        if turn_chars <= 0 and not any(_message_summary_text(m).strip() for m in turn):
            continue
        if kept_turns and total + turn_chars > max_chars:
            compressed_in_window += len(turn)
            continue
        kept_turns.insert(0, turn)
        total += turn_chars

    kept = _flatten_turns(kept_turns)

    if not kept and pool:
        last = pool[-1]
        flat = _message_summary_text(last)
        kept = [
            chat_message(
                str(last.get("role", "user")),
                flat[:max_chars],
            )
        ]

    dropped_count = dropped_by_window + compressed_in_window
    summary = ""
    if dropped_count > 0:
        kept_msg_count = len(kept)
        dropped_msgs = pool[: len(pool) - kept_msg_count]
        snippets = [
            f"- [{m.get('role', 'user')}] {snippet}"
            for m in dropped_msgs
            if (snippet := _extractive_snippet(m))
        ]
        if snippets:
            summary = (
                f"（已压缩较早的 {dropped_count} 条对话；保留最近 {kept_msg_count} 条，以下为摘要）\n"
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
    """将压缩摘要合并进首条 user，避免 assistant 摘要阻断 tool 配对。"""
    if not summary.strip():
        return history
    summary_text = summary.strip()
    if not history:
        return [chat_message("user", summary_text)]
    merged = list(history)
    first = merged[0]
    if str(first.get("role", "")) == "user":
        existing = message_content_text(first.get("content", "")).strip()
        merged_text = f"{summary_text}\n\n{existing}" if existing else summary_text
        merged[0] = chat_message("user", merged_text)
    else:
        merged.insert(0, chat_message("user", summary_text))
    return merged


MASTER_STATE_HEADER = "## 当前编排状态"
REACT_STATE_HEADER = MASTER_STATE_HEADER

MASTER_STATE_INSTRUCTIONS = """说明（每轮决策前必读）：
1. **必须通过 tool_calls 调用且只能调用**下方 JSON 的 `available_actions` 中提供的 function；角色说明中的行动全集仅供参考。
2. 委派子 Agent 使用 `delegate_agent`，传入 `agent_id`；`sub_agents` 列出各子 Agent 职责与就绪状态；`available_sub_agents` 为本轮可委派的 agent_id 列表（与工具 enum 一致）。
3. **硬性独占**：`delegate_agent` / `finish` / `ask_user_question` 本轮 tool_calls **只能各占一轮且不可与其他 function 并列**；禁止与 `tool_*` 同轮。若 observation 含「不可与其他 tool 同轮调用」，下一轮立即改为只调那一个独占 action。
4. 当必要步骤均已完成、available_actions 仅剩 `finish` 时，应选择 `finish`。
5. 勿根据对话历史中曾出现的行动，选用当前 available_actions 中已不存在的 action。
6. 若最近 observation 报告图片生成失败且建议修订提示词，script 步骤可能已重新开放，应先分析失败明细再决定是否 `delegate_agent(agent_id=script_agent)` 修 prompt。
7. **Store 复用**：启动时已将 `inferred_completed_steps` 写入 `completed_actions`（除非 `reopen_intent` 判定 full_redo / reopen_steps，或正则命中「全部重做」「重新配音」「从剪辑继续」等——该步及下游才会剔除）。若状态含 `reopen_intent.reopen_steps`，表示系统已重开这些步骤，可委派列表已更新。已有配音时勿再委派 tts_agent；据 `user_message` 与 `next_actions` 只补缺口；从剪辑继续且 `ready_for_edit_compose=true` 时优先 `editing_agent`。
8. **完整成片顺序**：`remaining_plan` 须遵守 canonical：`storyboard_refine_agent` 为剪辑前最后一步；AI 视频须 `video_agent` → `tts_agent` → `storyboard_refine_agent` → `editing_agent`（禁止复核后再生视频）。"""

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
        messages=repair_tool_message_pairs(messages),
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



def master_channel_has_user(
    conversations: ConversationStore,
    conversation_id: str,
) -> bool:
    """master 通道是否已有用户消息（主编排决策前置条件）。"""
    msgs = conversations.list_messages(conversation_id, "master")
    return any(m.role == MessageRole.USER for m in msgs)


def apply_snippet_chat_history(
    messages: list[ChatMessage],
    *,
    pin_first_user: bool = False,
) -> list[ChatMessage]:
    """同步 snippet 滑窗压缩并注入 assistant 摘要前缀。"""
    fitted, summary = fit_chat_history(messages, pin_first_user=pin_first_user)
    return repair_tool_message_pairs(_with_summary_prefix(fitted, summary))


def build_master_react_chat_history(
    conversations: ConversationStore,
    conversation_id: str,
) -> list[ChatMessage]:
    """主编排 ReAct：从 master 通道构建多轮 Chat 历史（不做主动压缩）。"""
    msgs = conversations.list_messages(conversation_id, "master")
    chat = messages_to_chat_history(msgs)
    return repair_tool_message_pairs(chat)


def build_agent_react_chat_history(
    conversations: ConversationStore,
    conversation_id: str,
    agent_name: str,
) -> list[ChatMessage]:
    """子 Agent ReAct / 行动：从 agent 通道构建多轮 Chat 历史（不含 TASK，任务由 anchor_user 注入）。"""
    msgs = conversations.list_messages(conversation_id, "agent", agent_name)
    chat = messages_to_chat_history(msgs, include_task=False)
    return repair_tool_message_pairs(chat)
