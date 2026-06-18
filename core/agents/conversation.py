"""Agent 对话隔离：主 Agent 与用户、子 Agent 与任务简报各自独立会话。"""

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
    script_id: str
    channel: Literal["master", "agent"]
    agent_name: str = ""  # channel=agent 时必填
    role: ConversationRole
    content: str


def conversation_key(script_id: str, channel: str, agent_name: str = "") -> str:
    if channel == "master":
        return f"{script_id}:master"
    return f"{script_id}:agent:{agent_name}"


class ConversationStore:
    """按 script + channel 隔离的多 Agent 会话存储。"""

    def __init__(self) -> None:
        self._messages: dict[str, list[ConversationMessage]] = {}

    def add(
        self,
        script_id: str,
        channel: Literal["master", "agent"],
        role: ConversationRole,
        content: str,
        agent_name: str = "",
    ) -> ConversationMessage:
        key = conversation_key(script_id, channel, agent_name)
        msg = ConversationMessage(
            script_id=script_id,
            channel=channel,
            agent_name=agent_name,
            role=role,
            content=content,
        )
        self._messages.setdefault(key, []).append(msg)
        return msg

    def list_messages(
        self,
        script_id: str,
        channel: Literal["master", "agent"],
        agent_name: str = "",
    ) -> list[ConversationMessage]:
        key = conversation_key(script_id, channel, agent_name)
        return list(self._messages.get(key, []))

    def clear_agent_session(self, script_id: str, agent_name: str) -> None:
        key = conversation_key(script_id, "agent", agent_name)
        self._messages.pop(key, None)
