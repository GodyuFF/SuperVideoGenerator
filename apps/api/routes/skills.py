"""REST API：Skill 列表。"""

from fastapi import APIRouter

from core.llm.prompt.skills import list_skills

router = APIRouter(prefix="/api")


@router.get("/skills")
def get_skills():
    """列出仓库内置 Skill（供 /skillId 补全）。"""
    return [
        {
            "id": meta.id,
            "title": meta.title,
            "description": meta.description,
            "aliases": list(meta.aliases),
        }
        for meta in list_skills()
    ]
