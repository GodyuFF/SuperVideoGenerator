"""按 Skill tool_manifest 过滤 ReAct available_actions。"""

from __future__ import annotations

from typing import Any

from core.extensions.protocol import SkillToolManifest
from core.llm.tools.shared.agent_tools import ASK_USER_QUESTION_ACTION

_PRESERVED_ACTIONS = frozenset({"finish", ASK_USER_QUESTION_ACTION})
# Skill 激活时默认追加的渐进加载工具（可用 exclude 关闭）
DEFAULT_SKILL_REF_TOOLS: tuple[str, ...] = ("list_skill_refs", "read_skill_ref")


def _parse_manifest(raw: dict[str, Any] | None) -> SkillToolManifest | None:
    """解析 skill_overlay 中的 tool_manifest。"""
    if not raw:
        return None
    return SkillToolManifest.from_dict(raw)


def apply_skill_tool_filter(
    agent_name: str,
    actions: list[str],
    skill_overlay: dict[str, Any] | None,
) -> list[str]:
    """按 skill_overlay.tool_manifest 过滤或追加 action；激活时默认追加 skill ref 工具。"""
    if not skill_overlay:
        return actions
    manifest = _parse_manifest(skill_overlay.get("tool_manifest"))
    exclude = set(manifest.exclude) if manifest else set()
    result = [a for a in actions if a not in exclude]

    whitelist = manifest.enabled_tools_for_agent(agent_name) if manifest else None
    if whitelist is not None:
        allowed = set(whitelist) | _PRESERVED_ACTIONS
        for tool in DEFAULT_SKILL_REF_TOOLS:
            if tool not in exclude:
                allowed.add(tool)
        return [a for a in result if a in allowed]

    if manifest and manifest.enable:
        seen = set(result)
        for tool in manifest.enable:
            if tool not in seen and tool not in exclude:
                result.append(tool)
                seen.add(tool)

    seen = set(result)
    for tool in DEFAULT_SKILL_REF_TOOLS:
        if tool not in exclude and tool not in seen:
            result.append(tool)
            seen.add(tool)
    return result


def apply_master_tool_filter(
    actions: list[str],
    skill_overlay: dict[str, Any] | None,
) -> list[str]:
    """主编排 tool_* 白名单（Skill tools.enable 中 tool_ 前缀）。"""
    if not skill_overlay:
        return actions
    manifest = _parse_manifest(skill_overlay.get("tool_manifest"))
    if manifest is None or not manifest.enable:
        return actions
    master_tools = [t for t in manifest.enable if t.startswith("tool_")]
    if not master_tools:
        return actions
    # 渐进加载相关主编排工具始终保留
    always = {
        "tool_list_skills",
        "tool_list_skill_refs",
        "tool_read_skill_ref",
        "tool_switch_skill",
    }
    allowed_master = set(master_tools) | always
    out: list[str] = []
    for action in actions:
        if action.startswith("tool_") and action not in allowed_master:
            continue
        out.append(action)
    return out
