"""ReAct 数据模型（无业务逻辑）。"""

from dataclasses import dataclass, field
from typing import Any

from core.models.entities import new_id


def new_conversation_id() -> str:
    """生成对话 id（对话开始时调用）。"""
    return new_id("conv")


@dataclass
class ReActAgentInfo:
    """Agent 角色信息。"""

    name: str
    display_name: str
    description: str


@dataclass
class ReActToolInfo:
    """可调用工具描述。"""

    action_name: str
    name: str
    description: str


@dataclass
class ReActStepRecord:
    """单轮 ReAct 记录。"""

    iteration: int
    thought: str
    action: str
    action_input: dict[str, Any] = field(default_factory=dict)
    observation: str | None = None
