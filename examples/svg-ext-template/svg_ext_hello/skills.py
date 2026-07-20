"""示例 Skill 提供器。"""

from __future__ import annotations

import json
from importlib.resources import files

from core.llm.prompt.skills.models import SkillBundle, SkillMeta
from core.extensions.protocol import SkillToolManifest


def get_skill_bundle() -> SkillBundle | None:
    """从包内 skills/hello/ 加载 Skill。"""
    root = files("svg_ext_hello") / "skills" / "hello"
    meta_raw = json.loads((root / "skill.json").read_text(encoding="utf-8"))
    meta = SkillMeta(
        id=str(meta_raw["id"]),
        title=str(meta_raw.get("title", meta_raw["id"])),
        description=str(meta_raw.get("description", "")),
        aliases=tuple(meta_raw.get("aliases") or []),
    )
    system_prompt = (root / "system.md").read_text(encoding="utf-8").strip()
    tools_raw = meta_raw.get("tools")
    tool_manifest = SkillToolManifest.from_dict(tools_raw if tools_raw else None)
    return SkillBundle(
        meta=meta,
        system_prompt=system_prompt,
        tool_manifest=tool_manifest,
        source="extension",
    )
