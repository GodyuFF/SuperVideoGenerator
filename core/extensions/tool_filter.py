"""按 Skill tool_manifest 过滤 ReAct available_actions。"""

from __future__ import annotations

from typing import Any

from core.extensions.protocol import SkillToolManifest
from core.llm.tools.shared.agent_tools import ASK_USER_QUESTION_ACTION

_PRESERVED_ACTIONS = frozenset({"finish", ASK_USER_QUESTION_ACTION})


def _parse_manifest(raw: dict[str, Any] | None) -> SkillToolManifest | None:
    if not raw:
        return None
    return SkillToolManifest.from_dict(raw)


def apply_skill_tool_filter(
    agent_name: str,
    actions: list[str],
    skill_overlay: dict[str, Any] | None,
) -> list[str]:
    """按 skill_overlay.tool_manifest 过滤或追加 action。"""
    if not skill_overlay:
        return actions
    manifest = _parse_manifest(skill_overlay.get("tool_manifest"))
    if manifest is None:
        return actions

    result = [a for a in actions if a not in set(manifest.exclude)]

    whitelist = manifest.enabled_tools_for_agent(agent_name)
    if whitelist is not None:
        allowed = set(whitelist) | _PRESERVED_ACTIONS
        return [a for a in result if a in allowed]

    if manifest.enable:
        seen = set(result)
        for tool in manifest.enable:
            if tool not in seen:
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
    allowed_master = set(master_tools)
    out: list[str] = []
    for action in actions:
        if action.startswith("tool_") and action not in allowed_master:
            continue
        out.append(action)
    return out
