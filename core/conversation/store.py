"""Agent 对话消息存储：按 conversation_id 隔离主会话与子 Agent 通道。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from core.llm.model.chat_message import (
    ContentBlock,
    thinking_block,
    tool_call_id_for_action,
    tool_use_block,
)
from core.models.entities import new_id


class MessageRole(str, Enum):
    """会话消息角色（对齐 Spring AI / OpenAI wire）。"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class MessageKind(str, Enum):
    """消息语义分类（非 wire role）。"""

    DEFAULT = "default"
    TASK_BRIEF = "task_brief"
    SUMMARY = "summary"


class ConversationMessage(BaseModel):
    """单条隔离会话消息。"""

    id: str = Field(default_factory=lambda: new_id("msg"))
    conversation_id: str
    project_id: str
    script_id: str
    channel: Literal["master", "agent"]
    agent_name: str = ""
    step_id: str = ""
    role: MessageRole
    content: str | list[ContentBlock]
    tool_call_id: str = ""
    message_kind: MessageKind = MessageKind.DEFAULT
    created_at: str = ""

    @field_validator("content", mode="before")
    @classmethod
    def _coerce_content(cls, value: Any) -> str | list[ContentBlock]:
        if value is None:
            return ""
        if isinstance(value, (str, list)):
            return value
        return str(value)


def load_conversation_messages(
    items: list[dict],
) -> list[ConversationMessage]:
    """从 JSON 列表加载消息。"""
    return [ConversationMessage.model_validate(i) for i in items]


def conversation_key(
    conversation_id: str,
    channel: str,
    agent_name: str = "",
) -> str:
    if channel == "master":
        return f"{conversation_id}:master"
    return f"{conversation_id}:agent:{agent_name}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationStore:
    """按 conversation_id + channel 隔离的多 Agent 会话存储。"""

    def __init__(
        self,
        sqlite_store: Any | None = None,
        write_queue: Any | None = None,
    ) -> None:
        self._messages: dict[str, list[ConversationMessage]] = {}
        self._agent_suspend: dict[str, dict[str, Any]] = {}
        self._sqlite = sqlite_store
        self._write_queue = write_queue

    def set_sqlite_store(self, sqlite_store: Any) -> None:
        self._sqlite = sqlite_store

    def set_write_queue(self, write_queue: Any) -> None:
        """注入异步批量写入队列。"""
        self._write_queue = write_queue

    @property
    def messages(self) -> dict[str, list[ConversationMessage]]:
        return self._messages

    def add(
        self,
        conversation_id: str,
        project_id: str,
        script_id: str,
        channel: Literal["master", "agent"],
        role: MessageRole,
        content: str | list[ContentBlock],
        agent_name: str = "",
        *,
        tool_call_id: str = "",
        message_kind: MessageKind = MessageKind.DEFAULT,
        step_id: str = "",
    ) -> ConversationMessage:
        key = conversation_key(conversation_id, channel, agent_name)
        msg = ConversationMessage(
            conversation_id=conversation_id,
            project_id=project_id,
            script_id=script_id,
            channel=channel,
            agent_name=agent_name,
            step_id=step_id,
            role=role,
            content=content,
            tool_call_id=tool_call_id,
            message_kind=message_kind,
            created_at=_utc_now(),
        )
        self._messages.setdefault(key, []).append(msg)
        if self._write_queue is not None:
            self._write_queue.enqueue(msg)
        elif self._sqlite is not None:
            self._sqlite.append_message(msg)
        return msg

    def add_user_message(
        self,
        conversation_id: str,
        project_id: str,
        script_id: str,
        content: str,
        *,
        channel: Literal["master", "agent"] = "master",
        agent_name: str = "",
    ) -> ConversationMessage:
        return self.add(
            conversation_id,
            project_id,
            script_id,
            channel,
            MessageRole.USER,
            content,
            agent_name,
        )

    def add_assistant_summary(
        self,
        conversation_id: str,
        project_id: str,
        script_id: str,
        content: str,
        *,
        channel: Literal["master", "agent"] = "master",
        agent_name: str = "",
    ) -> ConversationMessage:
        return self.add(
            conversation_id,
            project_id,
            script_id,
            channel,
            MessageRole.ASSISTANT,
            content,
            agent_name,
            message_kind=MessageKind.SUMMARY,
        )

    def add_task_brief(
        self,
        conversation_id: str,
        project_id: str,
        script_id: str,
        task_brief: str,
        agent_name: str,
    ) -> ConversationMessage:
        content = task_brief
        if not content.startswith("任务简报："):
            content = f"任务简报：{content}"
        return self.add(
            conversation_id,
            project_id,
            script_id,
            "agent",
            MessageRole.ASSISTANT,
            content,
            agent_name,
            message_kind=MessageKind.TASK_BRIEF,
        )

    def add_react_turn(
        self,
        conversation_id: str,
        project_id: str,
        script_id: str,
        *,
        thought: str,
        action: str,
        action_input: dict[str, Any],
        observation: str,
        channel: Literal["master", "agent"],
        agent_name: str = "",
        step_id: str = "",
        tool_call_id: str = "",
    ) -> tuple[ConversationMessage, ConversationMessage]:
        """写入一轮 ReAct：assistant（text + tool_use）+ tool（observation）。"""
        action_msg_id = new_id("msg")
        resolved_tool_id = tool_call_id.strip() or tool_call_id_for_action(action_msg_id)
        blocks: list[ContentBlock] = [thinking_block(thought)]
        blocks.append(
            tool_use_block(
                tool_id=resolved_tool_id,
                name=action,
                input_data=action_input,
            )
        )
        assistant_msg = self.add(
            conversation_id,
            project_id,
            script_id,
            channel,
            MessageRole.ASSISTANT,
            blocks,
            agent_name,
            step_id=step_id,
        )
        tool_msg = self.add(
            conversation_id,
            project_id,
            script_id,
            channel,
            MessageRole.TOOL,
            observation,
            agent_name,
            tool_call_id=resolved_tool_id,
            step_id=step_id,
        )
        return assistant_msg, tool_msg

    def add_react_turn_batch(
        self,
        conversation_id: str,
        project_id: str,
        script_id: str,
        *,
        thought: str,
        calls: list[tuple[str, str, dict[str, Any], str]],
        channel: Literal["master", "agent"],
        agent_name: str = "",
        step_id: str = "",
    ) -> tuple[ConversationMessage, list[ConversationMessage]]:
        """写入同轮多 tool ReAct：1 条 assistant（thinking + N tool_use）+ N 条 tool 消息。"""
        blocks: list[ContentBlock] = [thinking_block(thought)]
        tool_messages: list[ConversationMessage] = []
        resolved_calls: list[tuple[str, str, dict[str, Any], str]] = []
        for idx, (tool_call_id, action, action_input, observation) in enumerate(calls):
            resolved_id = tool_call_id.strip() or tool_call_id_for_action(f"{new_id('msg')}_{idx}")
            resolved_calls.append((resolved_id, action, action_input, observation))
            blocks.append(
                tool_use_block(
                    tool_id=resolved_id,
                    name=action,
                    input_data=action_input,
                )
            )
        assistant_msg = self.add(
            conversation_id,
            project_id,
            script_id,
            channel,
            MessageRole.ASSISTANT,
            blocks,
            agent_name,
            step_id=step_id,
        )
        for resolved_id, action, _action_input, observation in resolved_calls:
            tool_messages.append(
                self.add(
                    conversation_id,
                    project_id,
                    script_id,
                    channel,
                    MessageRole.TOOL,
                    observation,
                    agent_name,
                    tool_call_id=resolved_id,
                    step_id=step_id,
                )
            )
        return assistant_msg, tool_messages

    def add_orphan_observation(
        self,
        conversation_id: str,
        project_id: str,
        script_id: str,
        observation: str,
        *,
        channel: Literal["master", "agent"],
        agent_name: str = "",
    ) -> ConversationMessage:
        """无前置 action 的观察（如决策失败）。"""
        text = observation if observation.startswith("[观察]") else f"[观察] {observation}"
        return self.add(
            conversation_id,
            project_id,
            script_id,
            channel,
            MessageRole.ASSISTANT,
            text,
            agent_name,
        )

    def list_messages(
        self,
        conversation_id: str,
        channel: Literal["master", "agent"],
        agent_name: str = "",
    ) -> list[ConversationMessage]:
        key = conversation_key(conversation_id, channel, agent_name)
        return list(self._messages.get(key, []))

    def list_all_messages_for_conversation(
        self, conversation_id: str
    ) -> list[ConversationMessage]:
        """返回单对话全部 channel 的消息（用于时间线重建）。"""
        prefix = f"{conversation_id}:"
        items: list[ConversationMessage] = []
        for key, msgs in self._messages.items():
            if key.startswith(prefix):
                items.extend(msgs)
        return sorted(items, key=lambda m: (m.created_at, m.id))

    def list_master_messages_for_ui(
        self, conversation_id: str
    ) -> list[ConversationMessage]:
        """用户可见的主会话消息（user / assistant summary）。"""
        msgs = self.list_messages(conversation_id, "master")
        return [
            m
            for m in msgs
            if m.role == MessageRole.USER
            or (
                m.role == MessageRole.ASSISTANT
                and m.message_kind == MessageKind.SUMMARY
            )
        ]

    def clear_agent_session(self, conversation_id: str, agent_name: str) -> None:
        key = conversation_key(conversation_id, "agent", agent_name)
        self._messages.pop(key, None)

    def suspend_agent_session(
        self,
        conversation_id: str,
        agent_name: str,
        payload: dict[str, Any],
    ) -> None:
        key = conversation_key(conversation_id, "agent", agent_name)
        self._agent_suspend[key] = dict(payload)

    def pop_agent_suspend(
        self, conversation_id: str, agent_name: str
    ) -> dict[str, Any] | None:
        key = conversation_key(conversation_id, "agent", agent_name)
        return self._agent_suspend.pop(key, None)

    def clear(self) -> None:
        self._messages.clear()
        self._agent_suspend.clear()

    def delete_by_script_id(self, project_id: str, script_id: str) -> None:
        keys = [
            key
            for key, msgs in self._messages.items()
            if msgs
            and msgs[0].project_id == project_id
            and msgs[0].script_id == script_id
        ]
        for key in keys:
            del self._messages[key]

    def delete_by_project_id(self, project_id: str) -> None:
        keys = [
            key
            for key, msgs in self._messages.items()
            if msgs and msgs[0].project_id == project_id
        ]
        for key in keys:
            del self._messages[key]

    def load_dict(self, data: dict[str, list[ConversationMessage]]) -> None:
        self._messages = {k: list(v) for k, v in data.items()}
