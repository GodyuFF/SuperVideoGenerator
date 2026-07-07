"""Tool 调用结果（结构化 + ReAct observation）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from core.models.entities import StepOutput


class ToolResult(BaseModel):
    """MCP tools/call 等价返回。"""

    observation: str
    structured: dict[str, Any] = Field(default_factory=dict)
    outputs: list[StepOutput] = Field(default_factory=list)
    ok: bool = True
