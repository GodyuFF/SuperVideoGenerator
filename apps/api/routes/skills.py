"""REST API：Skill 列表、校验、导入与删除。"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from apps.api.state import state
from core.extensions.skill_registry import (
    list_all_skills,
    reset_skill_cache,
    skill_meta_extras,
)
from core.llm.prompt.skills.allowlist import filter_skill_metas_for_agent
from core.llm.prompt.skills.user_store import delete_user_skill, import_skill_from_zip
from core.llm.prompt.skills.validate import validate_skill_zip

router = APIRouter(prefix="/api")

MASTER_AGENT = "super_video_master"


class SkillImportResponse(BaseModel):
    """Skill 导入结果。"""

    id: str
    source: str = "user"
    message: str = ""
    validation: dict = Field(default_factory=dict)


class SkillValidateResponse(BaseModel):
    """Skill zip 格式校验结果（不落盘）。"""

    ok: bool
    skill_id: str | None = None
    title: str | None = None
    description: str = ""
    aliases: list[str] = Field(default_factory=list)
    already_exists: bool = False
    checks: list[dict] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _skill_item(meta) -> dict:
    """组装 Skill 列表项。"""
    item = {
        "id": meta.id,
        "title": meta.title,
        "description": meta.description,
        "aliases": list(meta.aliases),
        "highlights": list(getattr(meta, "highlights", ()) or ()),
    }
    item.update(skill_meta_extras(meta.id))
    return item


def _prune_skill_from_allowlists(skill_id: str) -> None:
    """从各 Profile 的 Agent Skill 白名单中移除已删除的 skill。"""
    sid = skill_id.strip().lower()
    data = state.agent_config.get_data()
    allowlists = data.skill_allowlists_by_profile or {}
    if not allowlists:
        return
    cleaned: dict[str, dict[str, list[str]]] = {}
    changed = False
    for profile_id, agents in allowlists.items():
        agent_map: dict[str, list[str]] = {}
        for agent_name, ids in (agents or {}).items():
            next_ids = [i for i in ids if i != sid]
            if len(next_ids) != len(ids):
                changed = True
            agent_map[agent_name] = next_ids
        cleaned[profile_id] = agent_map
    if changed:
        state.agent_config.update(skill_allowlists_by_profile=cleaned)


@router.get("/skills")
def get_skills(
    profile: str | None = Query(None, description="PromptProfile id，用于白名单过滤"),
    agent: str | None = Query(
        None,
        description="Agent 名；默认 super_video_master（对话选择器）",
    ),
):
    """列出内置、用户导入与扩展 Skill；可按 Profile×Agent 白名单过滤。"""
    metas = list_all_skills()
    if profile:
        agent_name = (agent or MASTER_AGENT).strip() or MASTER_AGENT
        allowlists = state.agent_config.get_data().skill_allowlists_by_profile
        metas = filter_skill_metas_for_agent(
            metas,
            profile_id=profile.strip(),
            agent_name=agent_name,
            skill_allowlists_by_profile=allowlists,
        )
    return [_skill_item(m) for m in metas]


@router.post("/skills/validate", response_model=SkillValidateResponse)
async def validate_skill(
    file: UploadFile = File(..., description="待校验的 Skill zip"),
):
    """校验 Skill zip 格式，不写入磁盘。"""
    raw = await file.read()
    report = validate_skill_zip(raw)
    return SkillValidateResponse(**report.to_dict())


@router.post("/skills/import", response_model=SkillImportResponse)
async def import_skill(
    file: UploadFile = File(..., description="Skill zip 包（含 skill.json）"),
    overwrite: bool = Form(False),
):
    """人工导入 Skill zip 到 data/skills；先完整格式校验。"""
    raw = await file.read()
    report = validate_skill_zip(raw)
    if not report.ok:
        raise HTTPException(
            400,
            {
                "message": report.errors[0] if report.errors else "Skill 格式校验失败",
                "validation": report.to_dict(),
            },
        )
    if report.already_exists and not overwrite:
        raise HTTPException(
            409,
            {
                "message": f"Skill「{report.skill_id}」已存在，请确认覆盖后重试",
                "validation": report.to_dict(),
            },
        )
    try:
        skill_id = import_skill_from_zip(raw, overwrite=True if report.already_exists else overwrite)
    except ValueError as exc:
        raise HTTPException(
            400,
            {"message": str(exc), "validation": report.to_dict()},
        ) from exc
    reset_skill_cache()
    return SkillImportResponse(
        id=skill_id,
        message=f"已导入 Skill「{skill_id}」",
        validation=report.to_dict(),
    )


@router.delete("/skills/{skill_id}")
def remove_skill(skill_id: str):
    """删除用户导入的 Skill（不可删内置/扩展），并清理白名单引用。"""
    try:
        delete_user_skill(skill_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _prune_skill_from_allowlists(skill_id)
    reset_skill_cache()
    return {"ok": True, "id": skill_id.strip().lower()}
