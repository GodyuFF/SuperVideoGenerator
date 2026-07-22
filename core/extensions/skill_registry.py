"""合并内置 / 用户导入 / svg.skills entry_points 的 Skill。"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from core.llm.prompt.skills.loader import (
    list_skills as list_builtin_skills,
    list_user_skills,
    load_user_skill,
)
from core.llm.prompt.skills.models import SkillBundle, SkillMeta
from core.llm.prompt.skills.user_store import is_user_skill

logger = logging.getLogger("core.extensions.skill_registry")

_EXTENSION_SKILLS: dict[str, SkillBundle] | None = None


def _load_extension_skills() -> dict[str, SkillBundle]:
    """扫描 entry_points 并缓存 SkillBundle。"""
    global _EXTENSION_SKILLS
    if _EXTENSION_SKILLS is not None:
        return _EXTENSION_SKILLS
    from core.extensions.constants import ENTRY_GROUP_SKILLS
    from core.extensions.discovery import call_all_entry_points

    result: dict[str, SkillBundle] = {}
    loaded: list[tuple[str, SkillBundle]] = []

    def _collect(name: str, provider) -> None:
        try:
            bundle = provider()
        except Exception:
            logger.exception("Skill entry_point 加载失败：%s", name)
            return
        if bundle is None:
            return
        bundle.source = getattr(bundle, "source", None) or "extension"
        loaded.append((name, bundle))

    call_all_entry_points(ENTRY_GROUP_SKILLS, on_call=_collect)
    for _name, bundle in loaded:
        result[bundle.meta.id] = bundle
    _EXTENSION_SKILLS = result
    return result


def reset_skill_cache() -> None:
    """清空扩展 / 用户 / 内置 Skill 缓存。"""
    global _EXTENSION_SKILLS
    _EXTENSION_SKILLS = None
    from core.llm.prompt.skills.loader import load_skill as _load_builtin
    from core.llm.prompt.skills.loader import load_user_skill as _load_user

    if hasattr(_load_builtin, "cache_clear"):
        _load_builtin.cache_clear()
    if hasattr(_load_user, "cache_clear"):
        _load_user.cache_clear()
    if hasattr(get_skill, "cache_clear"):
        get_skill.cache_clear()


@lru_cache(maxsize=64)
def get_skill(skill_id: str) -> SkillBundle | None:
    """加载 Skill：entry_points > 用户导入 > 内置。"""
    from core.llm.prompt.skills.loader import load_skill as load_builtin_skill

    skill_id = skill_id.strip().lower()
    ext = _load_extension_skills()
    if skill_id in ext:
        return ext[skill_id]
    user = load_user_skill(skill_id)
    if user is not None:
        return user
    bundle = load_builtin_skill(skill_id)
    if bundle is not None:
        bundle.source = "builtin"
    return bundle


def resolve_skill_id(token: str) -> str | None:
    """解析 skill id 或 alias。"""
    token = token.strip().lower()
    if not token:
        return None
    if get_skill(token) is not None:
        return token
    for meta in list_all_skills():
        if token in meta.aliases:
            return meta.id
    return None


def list_all_skills() -> list[SkillMeta]:
    """列出全部 Skill（用户/扩展覆盖同 id 内置）。"""
    by_id: dict[str, SkillMeta] = {}
    for meta in list_builtin_skills():
        by_id[meta.id] = meta
    for meta in list_user_skills():
        by_id[meta.id] = meta
    for bundle in _load_extension_skills().values():
        by_id[bundle.meta.id] = SkillMeta(
            id=bundle.meta.id,
            title=bundle.meta.title,
            description=bundle.meta.description,
            aliases=bundle.meta.aliases,
            highlights=getattr(bundle.meta, "highlights", ()) or (),
        )
    return sorted(by_id.values(), key=lambda m: m.id)


def skill_meta_extras(skill_id: str) -> dict[str, Any]:
    """API 列表用的 source / tools / 可删标志。"""
    bundle = get_skill(skill_id)
    if bundle is None:
        return {}
    source = getattr(bundle, "source", "builtin")
    extras: dict[str, Any] = {
        "source": source,
        "deletable": source == "user" or is_user_skill(skill_id),
    }
    if bundle.tool_manifest:
        extras["tools"] = bundle.tool_manifest.to_dict()
    return extras
