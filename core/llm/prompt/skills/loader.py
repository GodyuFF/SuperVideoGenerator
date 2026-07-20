"""从 core/llm/prompt/skills 目录加载 Skill 定义。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.llm.prompt.loader import prompt_root
from core.llm.prompt.skills.models import SkillBundle, SkillMeta
from core.extensions.protocol import SkillToolManifest

_SKILLS_ROOT = prompt_root() / "skills"


def skills_root() -> Path:
    return _SKILLS_ROOT


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _load_agent_overlays(skill_dir: Path) -> dict[str, str]:
    agents_dir = skill_dir / "agents"
    if not agents_dir.is_dir():
        return {}
    overlays: dict[str, str] = {}
    for path in agents_dir.glob("*.md"):
        overlays[path.stem] = path.read_text(encoding="utf-8").strip()
    return overlays


@lru_cache(maxsize=32)
def load_skill(skill_id: str) -> SkillBundle | None:
    skill_id = skill_id.strip().lower()
    skill_dir = _SKILLS_ROOT / skill_id
    if not skill_dir.is_dir():
        return None
    meta_raw = _read_json(skill_dir / "skill.json")
    declared_id = str(meta_raw.get("id", skill_id)).strip().lower()
    if declared_id != skill_id:
        return None
    aliases_raw = meta_raw.get("aliases") or []
    aliases = tuple(str(a).strip().lower() for a in aliases_raw if str(a).strip())
    meta = SkillMeta(
        id=skill_id,
        title=str(meta_raw.get("title", skill_id)),
        description=str(meta_raw.get("description", "")),
        aliases=aliases,
    )
    settings = _read_json(skill_dir / "settings.json")
    tools_raw = meta_raw.get("tools")
    if tools_raw is None:
        tools_raw = _read_json(skill_dir / "tools.json")
    tool_manifest = SkillToolManifest.from_dict(tools_raw if tools_raw else None)
    return SkillBundle(
        meta=meta,
        system_prompt=_read_text(skill_dir / "system.md"),
        settings=settings,
        agent_overlays=_load_agent_overlays(skill_dir),
        tool_manifest=tool_manifest,
        source="builtin",
    )


def list_skills() -> list[SkillMeta]:
    if not _SKILLS_ROOT.is_dir():
        return []
    result: list[SkillMeta] = []
    seen: set[str] = set()
    for child in sorted(_SKILLS_ROOT.iterdir()):
        if not child.is_dir():
            continue
        bundle = load_skill(child.name)
        if bundle is None or bundle.meta.id in seen:
            continue
        seen.add(bundle.meta.id)
        result.append(bundle.meta)
    return result


def resolve_skill_id(token: str) -> str | None:
    token = token.strip().lower()
    if not token:
        return None
    direct = load_skill(token)
    if direct is not None:
        return direct.meta.id
    for meta in list_skills():
        if token in meta.aliases:
            return meta.id
    return None
