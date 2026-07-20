"""Skill 元数据与加载结果。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.extensions.protocol import SkillToolManifest


@dataclass(frozen=True)
class SkillMeta:
    id: str
    title: str
    description: str = ""
    aliases: tuple[str, ...] = ()


@dataclass
class SkillBundle:
    meta: SkillMeta
    system_prompt: str = ""
    settings: dict[str, Any] = field(default_factory=dict)
    agent_overlays: dict[str, str] = field(default_factory=dict)
    tool_manifest: SkillToolManifest | None = None
    source: str = "builtin"

    def format_task_prefix(self) -> str:
        lines = [f"【Skill: {self.meta.title}】"]
        if self.system_prompt.strip():
            lines.append(self.system_prompt.strip())
        if self.settings:
            hints = []
            for key, val in self.settings.items():
                if val is None or val == "":
                    continue
                hints.append(f"{key}={val}")
            if hints:
                lines.append("设定：" + "；".join(hints))
        return "\n".join(lines)

    def agent_overlay(self, agent_name: str) -> str:
        return self.agent_overlays.get(agent_name, "").strip()

    def enabled_tools_for_agent(self, agent_name: str) -> list[str] | None:
        """Skill 激活时该 Agent 的 tool 白名单；None 表示不限制。"""
        if self.tool_manifest is None:
            return None
        return self.tool_manifest.enabled_tools_for_agent(agent_name)
