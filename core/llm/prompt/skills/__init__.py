"""Skill 单轮提示词与设定加载。"""

from core.extensions.skill_registry import (
    get_skill as load_skill,
    list_all_skills as list_skills,
    resolve_skill_id,
)
from core.llm.prompt.skills.loader import (
    list_skill_ref_entries,
    read_skill_ref_body,
    REF_BODY_MAX_CHARS,
)
from core.llm.prompt.skills.models import SkillBundle, SkillMeta, SkillRefIndexEntry
from core.llm.prompt.skills.parser import parse_skill_command

__all__ = [
    "REF_BODY_MAX_CHARS",
    "SkillBundle",
    "SkillMeta",
    "SkillRefIndexEntry",
    "list_skill_ref_entries",
    "list_skills",
    "load_skill",
    "parse_skill_command",
    "read_skill_ref_body",
    "resolve_skill_id",
]
