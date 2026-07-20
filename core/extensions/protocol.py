"""扩展包协议：Skill / Tool / MCP Server 注册契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from core.llm.prompt.skills.models import SkillBundle

from core.extensions.constants import (
    ENTRY_GROUP_MCP_SERVERS,
    ENTRY_GROUP_SKILLS,
    ENTRY_GROUP_TOOLS,
)

ToolRegistrar = Callable[["ToolRegistry"], None]
SkillProvider = Callable[[], "SkillBundle | None"]
McpServerProvider = Callable[[], dict[str, Any] | None]


@dataclass(frozen=True)
class ExtensionManifest:
    """扩展包元数据（可选，供文档与审计）。"""

    name: str
    version: str = ""
    description: str = ""


@dataclass
class SkillToolManifest:
    """Skill 激活时的 Tool 可见性声明。"""

    enable: list[str] = field(default_factory=list)
    agents: dict[str, list[str]] = field(default_factory=dict)
    exclude: list[str] = field(default_factory=list)
    mcp_servers: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> SkillToolManifest | None:
        """从 skill.json 的 tools 字段解析。"""
        if not raw or not isinstance(raw, dict):
            return None
        enable = [str(x).strip() for x in (raw.get("enable") or []) if str(x).strip()]
        exclude = [str(x).strip() for x in (raw.get("exclude") or []) if str(x).strip()]
        mcp_servers = [
            str(x).strip() for x in (raw.get("mcp_servers") or []) if str(x).strip()
        ]
        agents_raw = raw.get("agents") or {}
        agents: dict[str, list[str]] = {}
        if isinstance(agents_raw, dict):
            for agent_name, actions in agents_raw.items():
                if not isinstance(actions, list):
                    continue
                agents[str(agent_name).strip()] = [
                    str(a).strip() for a in actions if str(a).strip()
                ]
        if not (enable or exclude or agents or mcp_servers):
            return None
        return cls(
            enable=enable,
            agents=agents,
            exclude=exclude,
            mcp_servers=mcp_servers,
        )

    def enabled_tools_for_agent(self, agent_name: str) -> list[str] | None:
        """按 Agent 返回白名单；None 表示不限制默认 action 集合。"""
        if agent_name in self.agents:
            return list(self.agents[agent_name])
        return None

    def to_dict(self) -> dict[str, Any]:
        """序列化为 skill_overlay 可携带的结构。"""
        out: dict[str, Any] = {}
        if self.enable:
            out["enable"] = list(self.enable)
        if self.agents:
            out["agents"] = {k: list(v) for k, v in self.agents.items()}
        if self.exclude:
            out["exclude"] = list(self.exclude)
        if self.mcp_servers:
            out["mcp_servers"] = list(self.mcp_servers)
        return out


class ToolRegistrarProtocol(Protocol):
    """Tool 扩展注册器协议。"""

    def __call__(self, registry: Any) -> None: ...


class SkillProviderProtocol(Protocol):
    """Skill 扩展提供器协议。"""

    def __call__(self) -> "SkillBundle | None": ...
