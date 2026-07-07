"""从 SQLite 归档重建对话完整时间线（含 ReAct / 子 Agent / A2UI）。"""

from __future__ import annotations

import json
from typing import Any, Literal
from core.conversation.sqlite_store import A2UIRecord, ConversationSqliteStore
from core.conversation.store import ConversationMessage, MessageKind, MessageRole
from core.llm.master.session import build_master_sub_agents
from core.llm.model.chat_message import normalize_content

TimelineItem = dict[str, Any]

_AGENT_DISPLAY: dict[str, str] = {
    spec.agent_name: spec.display_name for spec in build_master_sub_agents()
}


def _display_name_for_agent(agent_name: str) -> str:
    if agent_name in _AGENT_DISPLAY:
        return _AGENT_DISPLAY[agent_name]
    from core.llm.master.actions import ACTION_TO_STEP, STEP_META

    if agent_name.startswith("delegate_"):
        step_type = ACTION_TO_STEP.get(agent_name)
        if step_type and step_type in STEP_META:
            return str(STEP_META[step_type].get("title", agent_name))
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


def _parse_react_assistant(msg: ConversationMessage) -> tuple[str, str, dict[str, Any]]:
    thought = ""
    action = ""
    action_input: dict[str, Any] = {}
    blocks = normalize_content(msg.content)
    for block in blocks:
        if block.get("type") == "text":
            thought = str(block.get("text", ""))
        elif block.get("type") == "tool_use":
            action = str(block.get("name", ""))
            raw_input = block.get("input", {})
            action_input = raw_input if isinstance(raw_input, dict) else {}
    return thought, action, action_input


def _agent_group_key(msg: ConversationMessage) -> str:
    if msg.step_id:
        return f"{msg.agent_name}:{msg.step_id}"
    return msg.agent_name or "agent"


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
            thought, action, action_input = _parse_react_assistant(msg)
            observation = ""
            if i + 1 < len(group_msgs) and group_msgs[i + 1].role == MessageRole.TOOL:
                observation = _content_text(group_msgs[i + 1].content)
                i += 2
            else:
                i += 1
            iter_no = len(iterations) + 1
            entry: dict[str, Any] = {"iteration": iter_no}
            if thought:
                entry["thought"] = thought
            if action:
                entry["action"] = action
            if action_input:
                entry["action_input"] = action_input
            if observation:
                entry["observation"] = observation
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
    status = "pending"
    if record.resolved_at:
        status = "submitted" if record.approved else "cancelled"
    values: dict[str, Any] = {}
    if record.response_json:
        values = dict(record.response_json.get("values") or {})
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
) -> list[TimelineItem]:
    """合并消息与 A2UI 记录，按时间排序并聚合 ReAct / 子 Agent。"""
    messages = sqlite_store.list_messages(conversation_id)
    a2ui_records = sqlite_store.list_a2ui(conversation_id)

    events: list[tuple[str, str, Literal["msg", "a2ui"], Any]] = []
    for msg in messages:
        events.append((msg.created_at, msg.id, "msg", msg))
    for rec in a2ui_records:
        events.append((rec.created_at, rec.id, "a2ui", rec))
    events.sort(key=lambda x: (x[0], x[1]))

    timeline: list[TimelineItem] = []
    master_react_iter = 0
    i = 0
    msg_events = [(e[2], e[3]) for e in events if e[2] == "msg"]
    msg_index = 0

    while i < len(events):
        _, _, kind, payload = events[i]
        if kind == "a2ui":
            timeline.append(_a2ui_timeline_item(payload))
            i += 1
            continue

        msg: ConversationMessage = payload
        if msg.channel == "agent":
            group_key = _agent_group_key(msg)
            group: list[ConversationMessage] = []
            j = i
            while j < len(events):
                _, _, k2, p2 = events[j]
                if k2 != "msg":
                    break
                m2: ConversationMessage = p2
                if m2.channel != "agent" or _agent_group_key(m2) != group_key:
                    break
                group.append(m2)
                j += 1
            item = _build_sub_agent_item(group)
            if item:
                timeline.append(item)
            i = j
            continue

        if msg.role == MessageRole.USER:
            timeline.append(
                {
                    "type": "user",
                    "content": _content_text(msg.content) if not isinstance(msg.content, str) else msg.content,
                    "created_at": msg.created_at,
                }
            )
            i += 1
            continue

        if msg.role == MessageRole.ASSISTANT and msg.message_kind == MessageKind.SUMMARY:
            content = msg.content if isinstance(msg.content, str) else _content_text(msg.content)
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
            thought, action, action_input = _parse_react_assistant(msg)
            observation = ""
            if (
                i + 1 < len(events)
                and events[i + 1][2] == "msg"
                and events[i + 1][3].role == MessageRole.TOOL
            ):
                observation = _content_text(events[i + 1][3].content)
                i += 2
            else:
                i += 1
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
