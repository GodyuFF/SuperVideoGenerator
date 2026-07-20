"""Tool 规格定义（对齐 MCP inputSchema / outputSchema）。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from core.llm.agent.react_core import AgentRunContext
from core.store.memory import MemoryStore

from core.llm.tools.result import ToolResult

ToolHandler = Callable[[MemoryStore, AgentRunContext, dict[str, Any]], ToolResult]


class ToolKind(str, Enum):
    READ = "read"
    WRITE_PIPELINE = "write_pipeline"
    WRITE_AD_HOC = "write_ad_hoc"
    AGENT_DELEGATE = "agent_delegate"


@dataclass(frozen=True)
class ToolSpec:
    """单源 tool 定义：schema + handler。"""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    agent: str
    kind: ToolKind
    handler: ToolHandler
    logical_name: str = ""  # 如 script.list_text_assets
    source: str = "builtin"  # builtin | extension | mcp

    @property
    def read_only(self) -> bool:
        return self.kind == ToolKind.READ

    @property
    def ad_hoc(self) -> bool:
        return self.kind == ToolKind.WRITE_AD_HOC
