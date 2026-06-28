"""Agent 对话消息存储：按 conversation_id 隔离主会话与子 Agent 通道。"""

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from core.models.entities import new_id


class ConversationRole(str, Enum):
    """会话消息角色。"""

    USER = "user"
    MASTER = "master"
    TASK = "task"  # 主 Agent 下发的任务简报（子 Agent 入口）
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"


class ConversationMessage(BaseModel):
    """单条隔离会话消息。"""

    id: str = Field(default_factory=lambda: new_id("msg"))
    conversation_id: str
    project_id: str
    script_id: str
    channel: Literal["master", "agent"]
    agent_name: str = ""  # channel=agent 时必填
    role: ConversationRole
    content: str
    created_at: str = ""


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

    def __init__(self) -> None:
        self._messages: dict[str, list[ConversationMessage]] = {}

    @property
    def messages(self) -> dict[str, list[ConversationMessage]]:
        return self._messages

    def add(
        self,
        conversation_id: str,
        project_id: str,
        script_id: str,
        channel: Literal["master", "agent"],
        role: ConversationRole,
        content: str,
        agent_name: str = "",
    ) -> ConversationMessage:
        key = conversation_key(conversation_id, channel, agent_name)
        msg = ConversationMessage(
            conversation_id=conversation_id,
            project_id=project_id,
            script_id=script_id,
            channel=channel,
            agent_name=agent_name,
            role=role,
            content=content,
            created_at=_utc_now(),
        )
        self._messages.setdefault(key, []).append(msg)
        return msg

    def list_messages(
        self,
        conversation_id: str,
        channel: Literal["master", "agent"],
        agent_name: str = "",
    ) -> list[ConversationMessage]:
        key = conversation_key(conversation_id, channel, agent_name)
        return list(self._messages.get(key, []))

    def list_master_messages_for_ui(
        self, conversation_id: str
    ) -> list[ConversationMessage]:
        """用户可见的主会话消息（user / master）。"""
        msgs = self.list_messages(conversation_id, "master")
        return [
            m
            for m in msgs
            if m.role in (ConversationRole.USER, ConversationRole.MASTER)
        ]

    def clear_agent_session(self, conversation_id: str, agent_name: str) -> None:
        key = conversation_key(conversation_id, "agent", agent_name)
        self._messages.pop(key, None)

    def clear(self) -> None:
        self._messages.clear()

    def load_dict(self, data: dict[str, list[ConversationMessage]]) -> None:
        self._messages = {k: list(v) for k, v in data.items()}
