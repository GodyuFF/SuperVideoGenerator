"""旧 ConversationRole 消息格式 → 四 Role 存储格式升级。"""

from __future__ import annotations

from typing import Any

from core.llm.model.chat_message import (
    parse_action_content,
    text_block,
    tool_call_id_for_action,
    tool_use_block,
)
from core.models.entities import new_id

_LEGACY_ROLES = frozenset(
    {"master", "task", "thought", "action", "observation"}
)


def _is_legacy_role(role: str) -> bool:
    return role in _LEGACY_ROLES


def upgrade_conversation_messages(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """将单通道消息列表从旧 7-role 格式升级为四 Role 格式。"""
    if not items:
        return []
    if not any(_is_legacy_role(str(m.get("role", ""))) for m in items):
        return items

    result: list[dict[str, Any]] = []
    i = 0
    while i < len(items):
        raw = dict(items[i])
        role = str(raw.get("role", ""))

        if role == "user":
            raw["role"] = "user"
            raw.setdefault("message_kind", "default")
            raw.setdefault("tool_call_id", "")
            result.append(raw)
            i += 1
            continue

        if role == "master":
            raw["role"] = "assistant"
            raw["message_kind"] = "summary"
            raw.setdefault("tool_call_id", "")
            result.append(raw)
            i += 1
            continue

        if role == "task":
            raw["role"] = "assistant"
            raw["message_kind"] = "task_brief"
            content = str(raw.get("content", ""))
            if not content.startswith("任务简报："):
                raw["content"] = f"任务简报：{content}"
            raw.setdefault("tool_call_id", "")
            result.append(raw)
            i += 1
            continue

        if role == "thought":
            thought = str(raw.get("content", ""))
            action_name = ""
            action_input: dict[str, Any] = {}
            action_msg_id = str(raw.get("id", new_id("msg")))
            tool_call_id = tool_call_id_for_action(action_msg_id)

            if i + 1 < len(items) and str(items[i + 1].get("role")) == "action":
                action_raw = items[i + 1]
                action_msg_id = str(action_raw.get("id", action_msg_id))
                tool_call_id = tool_call_id_for_action(action_msg_id)
                action_name, action_input = parse_action_content(
                    str(action_raw.get("content", ""))
                )
                i += 2
            else:
                i += 1

            blocks: list[dict[str, Any]] = []
            if thought:
                blocks.append(text_block(thought))
            if action_name:
                blocks.append(
                    tool_use_block(
                        tool_id=tool_call_id,
                        name=action_name,
                        input_data=action_input,
                    )
                )
            assistant_msg = {
                **raw,
                "id": action_msg_id if action_name else raw.get("id", new_id("msg")),
                "role": "assistant",
                "message_kind": "default",
                "tool_call_id": "",
                "content": blocks if blocks else thought,
            }
            result.append(assistant_msg)

            if i < len(items) and str(items[i].get("role")) == "observation":
                obs_raw = dict(items[i])
                result.append(
                    {
                        **obs_raw,
                        "role": "tool",
                        "message_kind": "default",
                        "tool_call_id": tool_call_id,
                        "content": str(obs_raw.get("content", "")),
                    }
                )
                i += 1
            continue

        if role == "action":
            action_msg_id = str(raw.get("id", new_id("msg")))
            tool_call_id = tool_call_id_for_action(action_msg_id)
            action_name, action_input = parse_action_content(
                str(raw.get("content", ""))
            )
            result.append(
                {
                    **raw,
                    "role": "assistant",
                    "message_kind": "default",
                    "tool_call_id": "",
                    "content": [
                        tool_use_block(
                            tool_id=tool_call_id,
                            name=action_name,
                            input_data=action_input,
                        )
                    ],
                }
            )
            i += 1
            if i < len(items) and str(items[i].get("role")) == "observation":
                obs_raw = dict(items[i])
                result.append(
                    {
                        **obs_raw,
                        "role": "tool",
                        "message_kind": "default",
                        "tool_call_id": tool_call_id,
                        "content": str(obs_raw.get("content", "")),
                    }
                )
                i += 1
            continue

        if role == "observation":
            result.append(
                {
                    **raw,
                    "role": "assistant",
                    "message_kind": "default",
                    "tool_call_id": "",
                    "content": f"[观察] {raw.get('content', '')}",
                }
            )
            i += 1
            continue

        raw.setdefault("message_kind", "default")
        raw.setdefault("tool_call_id", "")
        result.append(raw)
        i += 1

    return result
