"""从 SQLite 归档重建对话完整时间线（含 ReAct / 子 Agent / A2UI）。"""

from __future__ import annotations

from typing import Any, Literal

from core.conversation.sqlite_store import A2UIRecord, ConversationSqliteStore
from core.conversation.store import ConversationMessage, ConversationStore, MessageKind, MessageRole
from core.llm.master.session import build_master_sub_agents
from core.llm.model.chat_message import normalize_content

TimelineItem = dict[str, Any]

_AGENT_DISPLAY: dict[str, str] = {
    spec.agent_name: spec.display_name for spec in build_master_sub_agents()
}


def _display_name_for_agent(agent_name: str) -> str:
    if agent_name in _AGENT_DISPLAY:
        return _AGENT_DISPLAY[agent_name]
    from core.llm.agent.agent_registry import resolve_display_name

    if agent_name == "delegate_agent":
        return "委派子 Agent"
    try:
        return resolve_display_name(agent_name)
    except ValueError:
        return agent_name


def _content_text(content: str | list[dict[str, Any]]) -> str:
    blocks = normalize_content(content)
    parts: list[str] = []
    for block in blocks:
        if block.get("type") == "text":
            parts.append(str(block.get("text", "")))
        elif block.get("type") == "thinking":
            parts.append(str(block.get("thinking", "")))
    return "\n".join(p for p in parts if p).strip()


def _parse_react_assistant(
    msg: ConversationMessage,
) -> tuple[str, str, dict[str, Any], str]:
    """解析 ReAct assistant 消息，返回 thought、首个 action、action_input、tool_call_id。"""
    thought, calls = _parse_react_assistant_calls(msg)
    if not calls:
        return thought, "", {}, ""
    first = calls[0]
    return thought, first["action"], first["action_input"], first["tool_call_id"]


def _parse_react_assistant_calls(
    msg: ConversationMessage,
) -> tuple[str, list[dict[str, Any]]]:
    """解析 ReAct assistant 消息，返回 thought 与同轮全部 tool_use。"""
    thought = ""
    calls: list[dict[str, Any]] = []
    blocks = normalize_content(msg.content)
    for block in blocks:
        if block.get("type") == "text":
            thought = str(block.get("text", ""))
        elif block.get("type") == "thinking":
            thought = str(block.get("thinking", ""))
        elif block.get("type") == "tool_use":
            raw_input = block.get("input", {})
            calls.append(
                {
                    "action": str(block.get("name", "")),
                    "action_input": raw_input if isinstance(raw_input, dict) else {},
                    "tool_call_id": str(block.get("id", "") or ""),
                }
            )
    return thought, calls


def _agent_group_key(msg: ConversationMessage) -> str:
    if msg.step_id:
        return f"{msg.agent_name}:{msg.step_id}"
    return msg.agent_name or "agent"


def _collect_agent_groups(
    messages: list[ConversationMessage],
) -> dict[str, list[ConversationMessage]]:
    """按 step/agent 聚合全部子 Agent 消息（允许中间穿插主会话或 A2UI 事件）。"""
    groups: dict[str, list[ConversationMessage]] = {}
    for msg in messages:
        if msg.channel != "agent":
            continue
        key = _agent_group_key(msg)
        groups.setdefault(key, []).append(msg)
    return groups


def _merge_messages_for_timeline(
    sqlite_msgs: list[ConversationMessage],
    extra_msgs: list[ConversationMessage] | None,
) -> list[ConversationMessage]:
    """合并 SQLite 与内存消息，按时间与 ID 去重排序。"""
    if not extra_msgs:
        return list(sqlite_msgs)
    by_id = {m.id: m for m in sqlite_msgs}
    for msg in extra_msgs:
        by_id.setdefault(msg.id, msg)
    return sorted(by_id.values(), key=lambda m: (m.created_at, m.id))


def _find_tool_observation(
    events: list[tuple[str, str, Literal["msg", "a2ui"], Any]],
    start_idx: int,
    tool_call_id: str,
) -> tuple[str, int]:
    """在事件流中查找与 assistant 配对的 tool 观察（可跳过中间的 A2UI 等非 msg 事件）。"""
    for j in range(start_idx + 1, len(events)):
        kind = events[j][2]
        if kind != "msg":
            continue
        tool_msg: ConversationMessage = events[j][3]
        if tool_msg.role != MessageRole.TOOL:
            if tool_msg.channel == "master" and tool_msg.role == MessageRole.ASSISTANT:
                break
            continue
        if tool_call_id and tool_msg.tool_call_id != tool_call_id:
            continue
        return _content_text(tool_msg.content), j
    return "", start_idx


def _build_sub_agent_item(
    group_msgs: list[ConversationMessage],
) -> TimelineItem | None:
    if not group_msgs:
        return None
    agent_name = group_msgs[0].agent_name
    step_id = group_msgs[0].step_id or ""
    iterations: list[dict[str, Any]] = []
    i = 0
    while i < len(group_msgs):
        msg = group_msgs[i]
        if msg.role == MessageRole.ASSISTANT and msg.message_kind == MessageKind.TASK_BRIEF:
            i += 1
            continue
        if msg.role == MessageRole.ASSISTANT:
            thought, calls = _parse_react_assistant_calls(msg)
            if not calls:
                i += 1
                continue
            actions_detail: list[dict[str, Any]] = []
            j = i + 1
            for call in calls:
                observation = ""
                while j < len(group_msgs) and group_msgs[j].role == MessageRole.TOOL:
                    tool_msg = group_msgs[j]
                    if call["tool_call_id"] and tool_msg.tool_call_id != call["tool_call_id"]:
                        break
                    observation = _content_text(tool_msg.content)
                    j += 1
                    break
                actions_detail.append(
                    {
                        "action": call["action"],
                        "action_input": call["action_input"],
                        "observation": observation,
                    }
                )
            i = j
            iter_no = len(iterations) + 1
            entry: dict[str, Any] = {"iteration": iter_no}
            if thought:
                entry["thought"] = thought
            if len(actions_detail) == 1:
                entry["action"] = actions_detail[0]["action"]
                if actions_detail[0]["action_input"]:
                    entry["action_input"] = actions_detail[0]["action_input"]
                if actions_detail[0]["observation"]:
                    entry["observation"] = actions_detail[0]["observation"]
            else:
                entry["actions"] = actions_detail
                merged_obs = "\n".join(
                    f"{idx + 1}. {a['action']}: {a.get('observation', '')}"
                    for idx, a in enumerate(actions_detail)
                    if a.get("observation")
                )
                if merged_obs:
                    entry["observation"] = merged_obs
            iterations.append(entry)
            continue
        if msg.role == MessageRole.TOOL:
            i += 1
            continue
        if msg.role == MessageRole.ASSISTANT:
            text = _content_text(msg.content)
            if text:
                iterations.append({"iteration": len(iterations) + 1, "thought": text})
        i += 1
    if not iterations:
        return None
    return {
        "type": "sub_agent",
        "step_id": step_id,
        "agent_name": agent_name,
        "display_name": _display_name_for_agent(agent_name),
        "iterations": iterations,
        "created_at": group_msgs[0].created_at,
    }


def _a2ui_timeline_item(record: A2UIRecord) -> TimelineItem:
    """将 A2UI 持久化记录映射为时间线条目（含 expired）。"""
    values: dict[str, Any] = {}
    if record.response_json:
        values = dict(record.response_json.get("values") or {})
    status = "pending"
    if record.resolved_at:
        if str(values.get("intent", "")) == "expired":
            status = "expired"
        else:
            status = "submitted" if record.approved else "cancelled"
    return {
        "type": "a2ui_confirmation",
        "confirmation_id": record.confirmation_id,
        "request": record.request_json,
        "status": status,
        "submitted_values": values,
        "created_at": record.created_at,
    }


def build_conversation_timeline(
    conversation_id: str,
    sqlite_store: ConversationSqliteStore,
    *,
    conversation_store: ConversationStore | None = None,
) -> list[TimelineItem]:
    """合并消息与 A2UI 记录，按时间排序并聚合 ReAct / 子 Agent。"""
    sqlite_msgs = sqlite_store.list_messages(conversation_id)
    extra_msgs = (
        conversation_store.list_all_messages_for_conversation(conversation_id)
        if conversation_store is not None
        else None
    )
    messages = _merge_messages_for_timeline(sqlite_msgs, extra_msgs)
    a2ui_records = sqlite_store.list_a2ui(conversation_id)
    agent_groups = _collect_agent_groups(messages)
    emitted_agent_groups: set[str] = set()

    events: list[tuple[str, str, Literal["msg", "a2ui"], Any]] = []
    for msg in messages:
        events.append((msg.created_at, msg.id, "msg", msg))
    for rec in a2ui_records:
        events.append((rec.created_at, rec.id, "a2ui", rec))
    events.sort(key=lambda x: (x[0], x[1]))

    timeline: list[TimelineItem] = []
    master_react_iter = 0
    i = 0

    while i < len(events):
        _, _, kind, payload = events[i]
        if kind == "a2ui":
            timeline.append(_a2ui_timeline_item(payload))
            i += 1
            continue

        msg: ConversationMessage = payload
        if msg.channel == "agent":
            group_key = _agent_group_key(msg)
            if group_key not in emitted_agent_groups:
                item = _build_sub_agent_item(agent_groups.get(group_key, []))
                if item:
                    timeline.append(item)
                emitted_agent_groups.add(group_key)
            i += 1
            continue

        if msg.role == MessageRole.USER:
            timeline.append(
                {
                    "type": "user",
                    "content": _content_text(msg.content)
                    if not isinstance(msg.content, str)
                    else msg.content,
                    "created_at": msg.created_at,
                }
            )
            i += 1
            continue

        if msg.role == MessageRole.ASSISTANT and msg.message_kind == MessageKind.SUMMARY:
            content = (
                msg.content if isinstance(msg.content, str) else _content_text(msg.content)
            )
            timeline.append(
                {
                    "type": "assistant",
                    "content": content,
                    "created_at": msg.created_at,
                }
            )
            i += 1
            continue

        if msg.role == MessageRole.ASSISTANT:
            thought, action, action_input, tool_call_id = _parse_react_assistant(msg)
            observation, tool_idx = _find_tool_observation(events, i, tool_call_id)
            i = tool_idx + 1 if observation else i + 1
            if not action and not thought:
                text = _content_text(msg.content)
                if text.startswith("[观察]"):
                    timeline.append(
                        {
                            "type": "react_turn",
                            "iteration": master_react_iter + 1,
                            "thought": "",
                            "observation": text,
                            "created_at": msg.created_at,
                        }
                    )
                    master_react_iter += 1
                continue
            master_react_iter += 1
            item: TimelineItem = {
                "type": "react_turn",
                "iteration": master_react_iter,
                "thought": thought,
                "created_at": msg.created_at,
            }
            if action:
                item["action"] = action
            if action_input:
                item["action_input"] = action_input
            if observation:
                item["observation"] = observation
            timeline.append(item)
            continue

        if msg.role == MessageRole.TOOL:
            i += 1
            continue

        i += 1

    return timeline


def build_conversation_timeline_page(
    conversation_id: str,
    sqlite_store: ConversationSqliteStore,
    *,
    limit: int = 80,
    before_created_at: str | None = None,
    conversation_store: ConversationStore | None = None,
) -> tuple[list[TimelineItem], bool, str | None]:
    """分页构建对话时间线（最近 N 条 raw 消息窗口）。

    返回 (timeline, has_more, oldest_created_at)。
    oldest_created_at 为本窗口最早一条 raw 消息时间，供前端 before 游标继续向前翻页。
    """
    capped = max(1, min(limit, 500))
    sqlite_msgs = sqlite_store.list_messages_page(
        conversation_id,
        limit=capped,
        before_created_at=before_created_at,
    )
    has_more = len(sqlite_msgs) >= capped
    oldest_created_at = sqlite_msgs[0].created_at if sqlite_msgs else None
    extra_msgs = (
        conversation_store.list_all_messages_for_conversation(conversation_id)
        if conversation_store is not None
        else None
    )
    if extra_msgs and sqlite_msgs:
        earliest = sqlite_msgs[0].created_at
        extra_msgs = [m for m in extra_msgs if m.created_at >= earliest]
    messages = _merge_messages_for_timeline(sqlite_msgs, extra_msgs)
    a2ui_records = sqlite_store.list_a2ui(conversation_id)
    if before_created_at:
        a2ui_records = [r for r in a2ui_records if r.created_at < before_created_at]
    agent_groups = _collect_agent_groups(messages)
    emitted_agent_groups: set[str] = set()
    events: list[tuple[str, str, Literal["msg", "a2ui"], Any]] = []
    for msg in messages:
        events.append((msg.created_at, msg.id, "msg", msg))
    for rec in a2ui_records:
        events.append((rec.created_at, rec.id, "a2ui", rec))
    events.sort(key=lambda x: (x[0], x[1]))
    timeline: list[TimelineItem] = []
    master_react_iter = 0
    i = 0
    while i < len(events):
        _, _, kind, payload = events[i]
        if kind == "a2ui":
            timeline.append(_a2ui_timeline_item(payload))
            i += 1
            continue
        msg: ConversationMessage = payload
        if msg.channel == "agent":
            group_key = _agent_group_key(msg)
            if group_key not in emitted_agent_groups:
                item = _build_sub_agent_item(agent_groups.get(group_key, []))
                if item:
                    timeline.append(item)
                emitted_agent_groups.add(group_key)
            i += 1
            continue
        if msg.role == MessageRole.USER:
            timeline.append(
                {
                    "type": "user",
                    "content": _content_text(msg.content)
                    if not isinstance(msg.content, str)
                    else msg.content,
                    "created_at": msg.created_at,
                }
            )
            i += 1
            continue
        if msg.role == MessageRole.ASSISTANT and msg.message_kind == MessageKind.SUMMARY:
            content = (
                msg.content if isinstance(msg.content, str) else _content_text(msg.content)
            )
            timeline.append(
                {
                    "type": "assistant",
                    "content": content,
                    "created_at": msg.created_at,
                }
            )
            i += 1
            continue
        if msg.role == MessageRole.ASSISTANT:
            thought, action, action_input, tool_call_id = _parse_react_assistant(msg)
            observation, tool_idx = _find_tool_observation(events, i, tool_call_id)
            i = tool_idx + 1 if observation else i + 1
            if not action and not thought:
                text = _content_text(msg.content)
                if text.startswith("[观察]"):
                    timeline.append(
                        {
                            "type": "react_turn",
                            "iteration": master_react_iter + 1,
                            "thought": "",
                            "observation": text,
                            "created_at": msg.created_at,
                        }
                    )
                    master_react_iter += 1
                continue
            master_react_iter += 1
            item: TimelineItem = {
                "type": "react_turn",
                "iteration": master_react_iter,
                "thought": thought,
                "created_at": msg.created_at,
            }
            if action:
                item["action"] = action
            if action_input:
                item["action_input"] = action_input
            if observation:
                item["observation"] = observation
            timeline.append(item)
            continue
        if msg.role == MessageRole.TOOL:
            i += 1
            continue
        i += 1
    return timeline, has_more, oldest_created_at
