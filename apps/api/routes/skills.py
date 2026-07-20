"""REST API：Skill 列表。"""

from fastapi import APIRouter

from core.extensions.skill_registry import list_all_skills, skill_meta_extras

router = APIRouter(prefix="/api")


@router.get("/skills")
def get_skills():
    """列出内置与 entry_points 注册的 Skill（供 /skillId 补全）。"""
    result = []
    for meta in list_all_skills():
        item = {
            "id": meta.id,
            "title": meta.title,
            "description": meta.description,
            "aliases": list(meta.aliases),
        }
        item.update(skill_meta_extras(meta.id))
        result.append(item)
    return result
