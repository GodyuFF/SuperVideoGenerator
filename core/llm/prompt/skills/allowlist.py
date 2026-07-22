"""Agent Skill 可用性：按 Profile × Agent 白名单过滤。"""

from __future__ import annotations

from typing import Iterable

from core.extensions.skill_registry import list_all_skills
from core.llm.prompt.skills.models import SkillMeta


def normalize_skill_ids(raw: Iterable[str] | None) -> list[str]:
    """规范化 skill id 列表。"""
    if not raw:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        sid = str(item).strip().lower()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    return out


def agent_skill_allowlist(
    skill_allowlists_by_profile: dict[str, dict[str, list[str]]] | None,
    profile_id: str,
    agent_name: str,
) -> list[str] | None:
    """
    返回某 Agent 的 Skill 白名单。

    None = 未配置（全部可用）；list = 仅这些 id（可为空表示禁用全部）。
    """
    if not skill_allowlists_by_profile:
        return None
    by_agent = skill_allowlists_by_profile.get(profile_id) or {}
    if agent_name not in by_agent:
        return None
    return normalize_skill_ids(by_agent.get(agent_name))


def is_skill_allowed_for_agent(
    skill_id: str,
    *,
    profile_id: str,
    agent_name: str,
    skill_allowlists_by_profile: dict[str, dict[str, list[str]]] | None,
) -> bool:
    """判断 skill 是否允许用于指定 Agent。"""
    allow = agent_skill_allowlist(
        skill_allowlists_by_profile, profile_id, agent_name
    )
    if allow is None:
        return True
    return skill_id.strip().lower() in allow


def filter_skill_metas_for_agent(
    metas: list[SkillMeta] | None = None,
    *,
    profile_id: str,
    agent_name: str,
    skill_allowlists_by_profile: dict[str, dict[str, list[str]]] | None,
) -> list[SkillMeta]:
    """按 Agent 白名单过滤 Skill 元数据列表。"""
    items = metas if metas is not None else list_all_skills()
    allow = agent_skill_allowlist(
        skill_allowlists_by_profile, profile_id, agent_name
    )
    if allow is None:
        return list(items)
    allow_set = set(allow)
    return [m for m in items if m.id in allow_set]


def skill_overlay_for_agent(
    overlay: dict | None,
    *,
    profile_id: str,
    agent_name: str,
    skill_allowlists_by_profile: dict[str, dict[str, list[str]]] | None,
) -> dict | None:
    """若当前 Skill 不在该 Agent 白名单内则返回 None，否则原样返回 overlay。"""
    if not overlay:
        return None
    skill_id = str(overlay.get("id") or "").strip().lower()
    if not skill_id:
        return None
    if not is_skill_allowed_for_agent(
        skill_id,
        profile_id=profile_id,
        agent_name=agent_name,
        skill_allowlists_by_profile=skill_allowlists_by_profile,
    ):
        return None
    return overlay
