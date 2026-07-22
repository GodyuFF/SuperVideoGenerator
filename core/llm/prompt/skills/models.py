"""Skill 元数据与加载结果。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from core.extensions.protocol import SkillToolManifest


@dataclass(frozen=True)
class SkillMeta:
    """Skill 列表用元数据（L1）。"""

    id: str
    title: str
    description: str = ""
    aliases: tuple[str, ...] = ()
    # 作用亮点（配置页 / 添加抽屉展示）
    highlights: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillRefIndexEntry:
    """Skill references 索引条目（L3 目录，不含正文）。"""

    id: str
    title: str
    path: str
    summary: str = ""
    agents: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """序列化为 skill_overlay / API 可携带结构。"""
        return {
            "id": self.id,
            "title": self.title,
            "path": self.path,
            "summary": self.summary,
            "agents": list(self.agents),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> SkillRefIndexEntry:
        """从 dict 还原索引条目。"""
        agents_raw = raw.get("agents") or []
        agents = tuple(str(a).strip() for a in agents_raw if str(a).strip())
        return cls(
            id=str(raw.get("id", "")).strip(),
            title=str(raw.get("title", "")).strip(),
            path=str(raw.get("path", "")).strip(),
            summary=str(raw.get("summary", "")).strip(),
            agents=agents,
        )


@dataclass
class SkillBundle:
    """已加载的 Skill 包：L2 正文 + L3 索引（不含 references 全文）。"""

    meta: SkillMeta
    system_prompt: str = ""
    settings: dict[str, Any] = field(default_factory=dict)
    agent_overlays: dict[str, str] = field(default_factory=dict)
    ref_index: list[SkillRefIndexEntry] = field(default_factory=list)
    tool_manifest: SkillToolManifest | None = None
    source: str = "builtin"

    def format_ref_index_lines(
        self,
        *,
        agent_name: str | None = None,
    ) -> list[str]:
        """格式化参考索引行；可按 Agent 过滤。"""
        lines: list[str] = []
        for entry in self.ref_index:
            if agent_name and entry.agents and agent_name not in entry.agents:
                continue
            agent_hint = (
                f"（agents: {', '.join(entry.agents)}）" if entry.agents else ""
            )
            summary = entry.summary or "（无摘要）"
            lines.append(
                f"- {entry.id}：{entry.title} — {summary}{agent_hint}"
            )
        return lines

    def format_task_prefix(self) -> str:
        """主编排用户消息前缀：L2 + 参考索引（不含 L3 正文）。"""
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
        ref_lines = self.format_ref_index_lines()
        if ref_lines:
            lines.append("【可按需查阅的参考】")
            lines.extend(ref_lines)
            lines.append(
                "（使用 list_skill_refs / read_skill_ref 或主编排 tool_list_skill_refs / "
                "tool_read_skill_ref 拉取正文）"
            )
        return "\n".join(lines)

    def agent_overlay(self, agent_name: str) -> str:
        """返回指定 Agent 的 L2 overlay 文本。"""
        return self.agent_overlays.get(agent_name, "").strip()

    def enabled_tools_for_agent(self, agent_name: str) -> list[str] | None:
        """Skill 激活时该 Agent 的 tool 白名单；None 表示不限制。"""
        if self.tool_manifest is None:
            return None
        return self.tool_manifest.enabled_tools_for_agent(agent_name)

    def to_overlay_dict(self) -> dict[str, Any]:
        """构建 skill_overlay 轻量结构（供 session / work_context）。"""
        return {
            "id": self.meta.id,
            "title": self.meta.title,
            "agent_overlays": dict(self.agent_overlays),
            "ref_index": [e.to_dict() for e in self.ref_index],
            "tool_manifest": (
                self.tool_manifest.to_dict() if self.tool_manifest else None
            ),
            "mcp_servers": (
                list(self.tool_manifest.mcp_servers)
                if self.tool_manifest and self.tool_manifest.mcp_servers
                else []
            ),
        }
