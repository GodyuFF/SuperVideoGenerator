"""REST API：项目、剧本、配置、Plan/Execute。"""

import asyncio
import time
from pathlib import PurePath

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from apps.api.chat_job import run_chat_background
from apps.api.state import create_project, create_script, delete_project, delete_projects_batch, delete_script, state
from core.guards.script_style import ScriptStyleLockedError
from core.logging.perf import log_perf
from core.models.entities import GenerationMode, ExecutionMode, ImageSourceMode, PlanDocument, VideoStyleMode
from core.store import project_paths
from core.store.media_storage import absolute_media_path
from core.store.project_paths import absolute_export_path

router = APIRouter(prefix="/api")

_MEDIA_TYPE_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".zip": "application/zip",
}


class CreateProjectRequest(BaseModel):
    """创建项目请求体。"""

    title: str


class CreateScriptRequest(BaseModel):
    """创建剧本请求体。"""

    title: str
    duration_sec: int = 60
    style_mode: str | None = None  # 若提供则在创建时绑定并锁定风格


class UpdateConfigRequest(BaseModel):
    """更新项目配置请求体（不含视频风格，风格绑定在剧本级）。"""

    generation_mode: GenerationMode | None = None
    execution_mode: ExecutionMode | None = None
    require_plan_approval: bool | None = None
    image_source_mode: ImageSourceMode | None = None
    image_text_preset: str | None = None
    comic_preset: str | None = None
    image_batch_pending_assets: bool | None = None
    image_allow_search_fallback: bool | None = None


class ChatRequest(BaseModel):
    """用户对话请求：超级视频大师自动 Plan 并调度子 Agent 执行。"""

    message: str
    conversation_id: str | None = None
    generation_mode: GenerationMode | None = None
    execution_mode: ExecutionMode | None = None
    style_mode: str | None = None
    style_hints: dict[str, str] | None = None  # 可选通用提示词（image_style/target_duration），随风格锁定
    skill_id: str | None = None


class CreateConversationRequest(BaseModel):
    """显式创建对话线程。"""

    title: str = ""


class BatchDeleteProjectsRequest(BaseModel):
    """批量删除项目。"""

    project_ids: list[str]


@router.get("/projects")
def list_projects():
    """列出本地持久化的所有项目。"""
    projects = state.store.list_projects()
    result = []
    for p in projects:
        scripts = state.store.list_scripts_for_project(p.id)
        result.append(
            {
                **p.model_dump(),
                "script_count": len(scripts),
                "scripts": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "status": s.status.value,
                        "script_index": i,
                        "created_at": s.created_at or "",
                    }
                    for i, s in enumerate(scripts, start=1)
                ],
            }
        )
    return result


@router.post("/projects")
def post_project(body: CreateProjectRequest):
    """创建新项目。"""
    return create_project(body.title).model_dump()


@router.post("/projects/batch-delete")
def post_batch_delete_projects(body: BatchDeleteProjectsRequest):
    """批量删除项目及其磁盘目录、对话数据。"""
    if not body.project_ids:
        raise HTTPException(400, detail="project_ids 不能为空")
    results = delete_projects_batch(body.project_ids)
    failed = {pid: msg for pid, msg in results.items() if msg != "ok"}
    if failed and len(failed) == len(body.project_ids):
        raise HTTPException(404, detail=failed)
    return {"results": results, "deleted": [pid for pid, msg in results.items() if msg == "ok"]}


@router.delete("/projects/{project_id}")
def delete_project_route(project_id: str):
    """删除项目及其全部剧本、资产目录与对话数据。"""
    try:
        delete_project(project_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return {"ok": True, "project_id": project_id}


@router.delete("/projects/{project_id}/scripts/{script_id}")
def delete_script_route(project_id: str, script_id: str):
    """删除单个剧本及其资产目录与对话数据。"""
    try:
        delete_script(project_id, script_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return {"ok": True, "project_id": project_id, "script_id": script_id}


@router.get("/projects/{project_id}/scripts/{script_id}/assets/media/{filename}")
def get_script_media_file(project_id: str, script_id: str, filename: str):
    """返回剧本目录下已落盘的媒体文件（供前端 img/video 预览）。"""
    if PurePath(filename).name != filename or ".." in filename:
        raise HTTPException(400, detail="无效的文件名")
    if not state.store.get_project(project_id):
        raise HTTPException(404, detail="项目不存在")
    script = state.store.get_script(script_id)
    if script is None or script.project_id != project_id:
        raise HTTPException(404, detail="剧本不存在")
    from core.store.media_storage import resolve_script_media_absolute_path

    path = resolve_script_media_absolute_path(
        project_id, script_id, filename, store=state.store
    )
    if path is None:
        raise HTTPException(404, detail="媒体文件不存在")
    media_type = _MEDIA_TYPE_BY_EXT.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type)


@router.get("/projects/{project_id}/scripts/{script_id}/assets/exports/{filename}")
def get_script_export_file(project_id: str, script_id: str, filename: str):
    """返回剧本目录下已落盘的成片文件（供前端 video 预览）。"""
    if PurePath(filename).name != filename or ".." in filename:
        raise HTTPException(400, detail="无效的文件名")
    if not state.store.get_project(project_id):
        raise HTTPException(404, detail="项目不存在")
    script = state.store.get_script(script_id)
    if script is None or script.project_id != project_id:
        raise HTTPException(404, detail="剧本不存在")
    rel = project_paths.relative_export_path(project_id, script_id, filename)
    path = absolute_export_path(rel)
    if path is None:
        raise HTTPException(404, detail="成片文件不存在")
    media_type = _MEDIA_TYPE_BY_EXT.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type)


@router.post("/projects/{project_id}/scripts/{script_id}/assets/exports/{filename}/reveal")
def reveal_script_export_file(project_id: str, script_id: str, filename: str):
    """在系统文件管理器中定位已导出的成片（Windows/macOS/Linux）。"""
    from core.edit.export_reveal import reveal_path_in_file_manager

    if PurePath(filename).name != filename or ".." in filename:
        raise HTTPException(400, detail="无效的文件名")
    if not state.store.get_project(project_id):
        raise HTTPException(404, detail="项目不存在")
    script = state.store.get_script(script_id)
    if script is None or script.project_id != project_id:
        raise HTTPException(404, detail="剧本不存在")
    rel = project_paths.relative_export_path(project_id, script_id, filename)
    path = absolute_export_path(rel)
    if path is None:
        raise HTTPException(404, detail="成片文件不存在")
    try:
        reveal_path_in_file_manager(path)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    return {"ok": True, "path": str(path)}


@router.post("/projects/{project_id}/scripts/{script_id}/assets/media/{filename}/reveal")
def reveal_script_media_file(project_id: str, script_id: str, filename: str):
    """在系统文件管理器中定位剧本 media 目录下的媒体文件。"""
    from core.edit.export_reveal import reveal_path_in_file_manager

    if PurePath(filename).name != filename or ".." in filename:
        raise HTTPException(400, detail="无效的文件名")
    if not state.store.get_project(project_id):
        raise HTTPException(404, detail="项目不存在")
    script = state.store.get_script(script_id)
    if script is None or script.project_id != project_id:
        raise HTTPException(404, detail="剧本不存在")
    rel = project_paths.relative_media_path(project_id, script_id, filename)
    path = absolute_media_path(rel)
    if path is None:
        raise HTTPException(404, detail="媒体文件不存在")
    try:
        reveal_path_in_file_manager(path)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    return {"ok": True, "path": str(path)}


@router.get("/projects/{project_id}")
def get_project(project_id: str):
    """获取项目详情。"""
    project = state.store.get_project(project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    return project.model_dump()


@router.patch("/projects/{project_id}/config")
def patch_config(project_id: str, body: UpdateConfigRequest):
    """更新项目配置（生成模式、视频风格等）。"""
    project = state.store.get_project(project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if body.generation_mode is not None:
        project.config.generation.mode = body.generation_mode
    if body.execution_mode is not None:
        project.config.generation.execution_mode = body.execution_mode
    if body.require_plan_approval is not None:
        project.config.generation.require_plan_approval = body.require_plan_approval
    it = project.config.image_text
    if body.image_source_mode is not None:
        it.source_mode = body.image_source_mode
    if body.image_text_preset is not None:
        it.image_text_preset = body.image_text_preset  # type: ignore[assignment]
    if body.comic_preset is not None:
        it.comic_preset = body.comic_preset  # type: ignore[assignment]
    if body.image_batch_pending_assets is not None:
        it.batch_pending_assets = body.image_batch_pending_assets
    if body.image_allow_search_fallback is not None:
        it.allow_search_fallback = body.image_allow_search_fallback
    return project.config.model_dump()


@router.post("/projects/{project_id}/scripts")
def post_script(project_id: str, body: CreateScriptRequest):
    """在项目下创建剧本。"""
    if not state.store.get_project(project_id):
        raise HTTPException(404, "项目不存在")
    project = state.store.get_project(project_id)
    script = create_script(project_id, body.title, body.duration_sec)
    if body.style_mode is not None and project:
        from core.guards.script_style import bind_script_style

        bind_script_style(script, project, body.style_mode)
    return script.model_dump()


@router.get("/projects/{project_id}/scripts/{script_id}")
def get_script(project_id: str, script_id: str):
    """获取剧本详情。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    return script.model_dump()


@router.get("/projects/{project_id}/scripts/{script_id}/assets")
def list_assets(project_id: str, script_id: str, type: str | None = None):
    """列出当前剧本可见资产（私有 + 已关联共享池）；type 可过滤 character/prop/scene/frame/plot/narration。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    assets = state.store.list_visible_text_assets_for_script(script_id)
    if type:
        assets = [a for a in assets if a.type.value == type]
    return [a.model_dump() for a in assets]


@router.post("/projects/{project_id}/scripts/{script_id}/assets/reapply-chroma")
async def reapply_chroma_for_script_assets(
    project_id: str,
    script_id: str,
    force: bool = False,
):
    """对 character/prop 关联图片重新绿幕抠图（修复未抠图的历史资产）。"""
    import asyncio

    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    from core.assets.chroma_key import reapply_chroma_for_script
    from core.store.persist import schedule_save

    result = await asyncio.to_thread(
        reapply_chroma_for_script,
        state.store,
        project_id=project_id,
        script_id=script_id,
        force=force,
    )
    schedule_save(state.store, immediate=True)
    return result


class RegenerateAssetRequest(BaseModel):
    """单资产二次生成请求体。"""

    variant_id: str | None = None


class RegenerateShotRequest(BaseModel):
    """分镜级二次生成请求体。"""

    kinds: list[str] = ["tts"]
    video: dict | None = None


def _master_active(script_id: str) -> bool:
    """判断剧本是否仍有进行中的主编排任务。"""
    from core.execution.cancel import get_execution_cancel_registry

    registry = get_execution_cancel_registry()
    return registry.is_active(script_id) or state.is_chat_running(script_id)


@router.post(
    "/projects/{project_id}/scripts/{script_id}/assets/{asset_id}/regenerate",
    status_code=202,
)
async def regenerate_asset_route(
    project_id: str,
    script_id: str,
    asset_id: str,
    body: RegenerateAssetRequest | None = None,
):
    """详情页：对单个资产发起二次生成（生图 / TTS / 视频）。"""
    from core.assets.regenerate import (
        RegenerateError,
        assert_regenerate_allowed,
        asset_label_for_queue,
        infer_generation_queue_kind,
        regenerate_asset,
    )
    from core.generation.queue import get_generation_queue

    if not state.store.get_project(project_id):
        raise HTTPException(404, "项目不存在")
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")

    variant_id = body.variant_id if body else None
    kind = infer_generation_queue_kind(state.store, asset_id)
    if kind is not None:
        try:
            assert_regenerate_allowed(
                state.store,
                script,
                master_active=_master_active(script_id),
            )
        except RegenerateError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc

        label = asset_label_for_queue(state.store, asset_id)
        job = await get_generation_queue().enqueue(
            project_id=project_id,
            script_id=script_id,
            kind=kind,
            asset_id=asset_id,
            label=label,
            source="regenerate",
            variant_id=variant_id,
        )
        return JSONResponse(
            status_code=202,
            content={
                "accepted": True,
                "job_id": job.id,
                "asset_id": asset_id,
                "kind": kind,
                "ok": True,
                "message": "已加入生成队列",
                "snapshot": get_generation_queue().snapshot_for_script(script_id),
            },
        )

    try:
        result = await regenerate_asset(
            state.store,
            state.emitter,
            project_id=project_id,
            script_id=script_id,
            asset_id=asset_id,
            variant_id=variant_id,
            master_active=_master_active(script_id),
        )
    except RegenerateError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc

    await state.persist_store_async()
    return {
        "job_id": result.job_id,
        "asset_id": result.asset_id,
        "asset_ids": result.asset_ids,
        "kind": result.kind,
        "ok": result.ok,
        "message": result.message,
    }


@router.post(
    "/projects/{project_id}/scripts/{script_id}/shots/{shot_id}/regenerate",
    status_code=202,
)
async def regenerate_shot_route(
    project_id: str,
    script_id: str,
    shot_id: str,
    body: RegenerateShotRequest | None = None,
):
    """分镜详情抽屉：按 kinds 二次生成 TTS / 画面 / AI 视频。"""
    from core.assets.regenerate import (
        RegenerateError,
        RegenerateResult,
        ShotRegenerateKind,
        VideoRegenerateOptions,
        _regenerate_shot_tts,
        assert_regenerate_allowed,
        asset_label_for_queue,
        build_regenerate_context,
        build_shot_video_enqueue_payload,
        _resolve_shot_frame_asset_id,
        _resolve_shot_video_clip_asset_id,
    )
    from core.generation.queue import get_generation_queue

    if not state.store.get_project(project_id):
        raise HTTPException(404, "项目不存在")
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")

    raw_kinds = (body.kinds if body else None) or ["tts"]
    allowed: set[str] = {"tts", "frame", "video"}
    kinds: list[ShotRegenerateKind] = []
    for k in raw_kinds:
        key = str(k).strip().lower()
        if key not in allowed:
            raise HTTPException(400, f"不支持的 kinds 值：{k}，允许 tts / frame / video")
        if key not in kinds:
            kinds.append(key)  # type: ignore[arg-type]

    video_options = VideoRegenerateOptions.from_payload(body.video if body else None)

    plan = state.store.get_video_plan_for_script(script_id)
    if not plan or not any(s.id == shot_id for s in plan.shots):
        raise HTTPException(404, f"镜头 {shot_id} 不存在")

    try:
        assert_regenerate_allowed(
            state.store,
            script,
            master_active=_master_active(script_id),
        )
    except RegenerateError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc

    queue_kinds = [k for k in kinds if k in ("frame", "video")]
    direct_kinds = [k for k in kinds if k == "tts"]

    tts_result: RegenerateResult | None = None
    if direct_kinds:
        ctx = build_regenerate_context(
            store=state.store,
            emitter=state.emitter,
            project_id=project_id,
            script_id=script_id,
        )
        try:
            tts_result = await _regenerate_shot_tts(state.store, ctx, shot_id)
        except RegenerateError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc
        await state.persist_store_async()

    enqueued_jobs: list = []
    if queue_kinds:
        queue = get_generation_queue()
        for kind in queue_kinds:
            if kind == "frame":
                frame_id = _resolve_shot_frame_asset_id(state.store, script_id, shot_id)
                if not frame_id:
                    raise HTTPException(
                        400,
                        f"镜头 {shot_id} 未绑定 frame 画面资产，无法重新生图。",
                    )
                job = await queue.enqueue(
                    project_id=project_id,
                    script_id=script_id,
                    kind="image",
                    asset_id=frame_id,
                    label=asset_label_for_queue(state.store, frame_id),
                    source="regenerate",
                )
                enqueued_jobs.append(job)
            elif kind == "video":
                clip_id = _resolve_shot_video_clip_asset_id(
                    state.store, script_id, shot_id
                )
                if clip_id:
                    job = await queue.enqueue(
                        project_id=project_id,
                        script_id=script_id,
                        kind="video",
                        asset_id=clip_id,
                        label=asset_label_for_queue(state.store, clip_id),
                        source="regenerate",
                    )
                else:
                    payload = build_shot_video_enqueue_payload(
                        shot_id,
                        video_options=video_options,
                    )
                    job = await queue.enqueue(
                        project_id=project_id,
                        script_id=script_id,
                        kind="video",
                        asset_id=shot_id,
                        label=f"镜头 {shot_id} AI 视频",
                        source="regenerate",
                        payload=payload,
                    )
                enqueued_jobs.append(job)

    if enqueued_jobs:
        snapshot = get_generation_queue().snapshot_for_script(script_id)
        return JSONResponse(
            status_code=202,
            content={
                "accepted": True,
                "job_id": enqueued_jobs[-1].id,
                "job_ids": [j.id for j in enqueued_jobs],
                "asset_id": enqueued_jobs[-1].asset_id,
                "kind": "mixed" if len(enqueued_jobs) > 1 else enqueued_jobs[-1].kind,
                "ok": True,
                "message": "已加入生成队列",
                "snapshot": snapshot,
                **(
                    {
                        "tts_ok": tts_result.ok,
                        "tts_message": tts_result.message,
                    }
                    if tts_result is not None
                    else {}
                ),
            },
        )

    if tts_result is not None:
        return {
            "job_id": tts_result.job_id,
            "asset_id": tts_result.asset_id,
            "asset_ids": tts_result.asset_ids,
            "kind": tts_result.kind,
            "ok": tts_result.ok,
            "message": tts_result.message,
        }

    raise HTTPException(400, "请指定至少一种二次生成类型：tts / frame / video")


class PatchTextAssetRequest(BaseModel):
    """PATCH 图文资产请求体。"""

    name: str | None = None
    content: dict | None = None
    primary_media_id: str | None = None
    force_recompose_prompt: bool = False
    prompt_locked: bool | None = None


class PatchScriptRequest(BaseModel):
    """用户手动更新剧本。"""

    title: str | None = None
    content_md: str | None = None
    duration_sec: int | None = None


class CreateTextAssetRequest(BaseModel):
    """用户手动创建文字资产。"""

    type: str
    name: str
    content: dict | None = None


class GenerateTextAssetDraftRequest(BaseModel):
    """工作台 AI 生成图文资产草稿。"""

    asset_type: str
    summary: str
    name: str = ""
    hints: dict | None = None


@router.post("/projects/{project_id}/scripts/{script_id}/assets/generate-draft")
async def generate_text_asset_draft_route(
    project_id: str, script_id: str, body: GenerateTextAssetDraftRequest
):
    """根据摘要调用配置 LLM 生成角色/空镜/物品/画面完整 content JSON（工作台专用）。"""
    from core.assets.text_asset_draft import generate_text_asset_draft_for_script
    from core.guards.reference import ScriptEditGuardError

    if not state.store.get_project(project_id):
        raise HTTPException(404, "项目不存在")
    try:
        result = await generate_text_asset_draft_for_script(
            state.store,
            state.llm_config,
            project_id=project_id,
            script_id=script_id,
            asset_type=body.asset_type,
            summary=body.summary,
            name=body.name,
            hints=body.hints,
            interaction_recorder=state.interaction_recorder,
        )
    except ScriptEditGuardError as exc:
        raise HTTPException(403, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result


@router.patch("/projects/{project_id}/scripts/{script_id}")
async def patch_script_route(
    project_id: str, script_id: str, body: PatchScriptRequest
):
    """用户手动更新剧本标题/正文等。"""
    from core.assets.user_crud import user_patch_script
    from core.guards.reference import ScriptEditGuardError

    if not state.store.get_project(project_id):
        raise HTTPException(404, "项目不存在")
    try:
        script = user_patch_script(
            state.store,
            project_id=project_id,
            script_id=script_id,
            title=body.title,
            content_md=body.content_md,
            duration_sec=body.duration_sec,
        )
    except ScriptEditGuardError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await state.persist_store_async()
    await state.emitter.emit(
        {
            "type": "assets_changed",
            "script_id": script_id,
            "action": "patch_script",
        }
    )
    data = script.model_dump()
    data["editable"] = True
    return data


@router.post("/projects/{project_id}/scripts/{script_id}/assets")
async def post_text_asset_route(
    project_id: str, script_id: str, body: CreateTextAssetRequest
):
    """用户手动创建剧情/角色/场景/物品/画面资产。"""
    from core.assets.user_crud import user_create_text_asset
    from core.guards.reference import ScriptEditGuardError

    if not state.store.get_project(project_id):
        raise HTTPException(404, "项目不存在")
    try:
        asset = user_create_text_asset(
            state.store,
            project_id=project_id,
            script_id=script_id,
            asset_type=body.type,
            name=body.name,
            content=body.content,
        )
    except ScriptEditGuardError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await state.persist_store_async()
    await state.emitter.emit(
        {
            "type": "assets_changed",
            "script_id": script_id,
            "action": "create_asset",
            "asset_id": asset.id,
        }
    )
    return asset.model_dump()


@router.delete("/projects/{project_id}/scripts/{script_id}/assets/{asset_id}")
async def delete_text_asset_route(
    project_id: str, script_id: str, asset_id: str
):
    """用户手动删除剧本关联的文字资产。"""
    from core.assets.user_crud import AssetDeleteBlockedError, user_delete_text_asset
    from core.guards.reference import ScriptEditGuardError

    if not state.store.get_project(project_id):
        raise HTTPException(404, "项目不存在")
    try:
        user_delete_text_asset(
            state.store,
            project_id=project_id,
            script_id=script_id,
            asset_id=asset_id,
        )
    except AssetDeleteBlockedError as exc:
        raise HTTPException(
            409,
            detail={
                "message": str(exc),
                "asset_id": exc.asset_id,
                "references": [e.model_dump() for e in exc.references],
            },
        ) from exc
    except ScriptEditGuardError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await state.persist_store_async()
    await state.emitter.emit(
        {
            "type": "assets_changed",
            "script_id": script_id,
            "action": "delete_asset",
            "asset_id": asset_id,
        }
    )
    return {"ok": True, "asset_id": asset_id}


@router.patch("/projects/{project_id}/assets/{asset_id}")
async def patch_text_asset_route(
    project_id: str, asset_id: str, body: PatchTextAssetRequest
):
    """更新角色/物品/场景图文资产（用户编辑）。"""
    from core.assets.user_crud import user_patch_text_asset
    from core.guards.reference import ScriptEditGuardError

    if not state.store.get_project(project_id):
        raise HTTPException(404, "项目不存在")
    try:
        asset = user_patch_text_asset(
            state.store,
            project_id=project_id,
            asset_id=asset_id,
            name=body.name,
            content=body.content,
            primary_media_id=body.primary_media_id,
            force_recompose_prompt=body.force_recompose_prompt,
            prompt_locked=body.prompt_locked,
        )
    except ScriptEditGuardError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    await state.persist_store_async()
    script_id = asset.source_script_id
    if not script_id:
        for ref in state.store.references.values():
            if ref.target_id == asset.id and ref.script_id:
                script_id = ref.script_id
                break
    if script_id:
        await state.emitter.emit(
            {
                "type": "assets_changed",
                "script_id": script_id,
                "action": "patch_asset",
                "asset_id": asset.id,
            }
        )
    return asset.model_dump()


@router.get("/projects/{project_id}/assets/{asset_id}/lineage")
def get_asset_lineage(project_id: str, asset_id: str):
    """返回单资产的完整谱系（incoming/outgoing 关联边）。"""
    from core.assets.lineage import build_lineage

    if not state.store.get_project(project_id):
        raise HTTPException(404, "项目不存在")
    view = build_lineage(state.store, project_id, asset_id)
    if view is None:
        raise HTTPException(404, "资产不存在")
    if view.asset.project_id and view.asset.project_id != project_id:
        raise HTTPException(404, "资产不属于该项目")
    return view.model_dump()


@router.get("/projects/{project_id}/assets/{asset_id}/resolved-prompt")
def get_resolved_prompt(project_id: str, asset_id: str):
    """返回与生图/生视频一致的实际生成提示词（含参考图说明，只读）。"""
    from core.assets.resolved_prompt import (
        ResolvedPromptNotFoundError,
        ResolvedPromptUnsupportedError,
        build_resolved_prompt,
    )

    if not state.store.get_project(project_id):
        raise HTTPException(404, "项目不存在")
    try:
        return build_resolved_prompt(state.store, project_id, asset_id)
    except ResolvedPromptNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ResolvedPromptUnsupportedError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/projects/{project_id}/scripts/{script_id}/graph")
def get_script_graph(project_id: str, script_id: str):
    """返回剧本级资产关系子图（nodes + edges）。"""
    from core.assets.lineage import build_project_graph

    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    try:
        nodes, edges, stats = build_project_graph(
            state.store, project_id, script_id=script_id
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {
        "nodes": [n.model_dump() for n in nodes],
        "edges": [e.model_dump() for e in edges],
        "stats": stats,
    }


@router.get("/projects/{project_id}/scripts/{script_id}/plan")
def get_plan(project_id: str, script_id: str):
    """获取当前 PlanDocument；未对话/未生成时返回空计划（200），非 404。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    plan = state.store.get_plan(script_id)
    if not plan:
        return PlanDocument().model_dump()
    return plan.model_dump()


@router.get("/projects/{project_id}/scripts/{script_id}/video-plan")
def get_video_plan(project_id: str, script_id: str):
    """获取分镜视频计划稿；未生成时返回空 VideoPlan + 空 shot_timings（200），非 404。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    from core.edit.shot_detail_sync import (
        lazy_sync_storyboard_if_needed,
        refresh_shot_tts_durations_if_drifted,
    )

    changed = lazy_sync_storyboard_if_needed(state.store, script_id)
    refreshed, _ = refresh_shot_tts_durations_if_drifted(state.store, script_id)
    if changed or refreshed:
        from core.store.persist import schedule_save

        schedule_save(
            state.store,
            conversation_index=state.conversation_index,
            conversation_store=None,
        )
    from core.edit.video_plan_service import get_video_plan_view

    return get_video_plan_view(state.store, script_id)


class PatchVideoPlanShotRequest(BaseModel):
    """单镜 patch 请求体（镜内多轨结构）。"""

    title: str | None = None
    summary: str | None = None
    duration_ms: int | None = None
    review_note: str | None = None
    display_instructions: str | None = None
    camera_motion_refined: str | None = None
    need_regen: bool | None = None
    regen_reason: str | None = None
    sync_policy: str | None = None
    lip_sync_required: bool | None = None
    sync_notes: str | None = None
    proposed_sync_actions: list[dict] | None = None
    sub_shots: list[dict] | None = None
    video_tracks: list[dict] | None = None
    audio_tracks: list[dict] | None = None
    subtitles: list[dict] | None = None


class VideoPlanOpsRequest(BaseModel):
    """分镜结构性 ops 请求体。"""

    ops: list[dict]
    expected_revision: int | None = None


@router.patch("/projects/{project_id}/scripts/{script_id}/video-plan/shots/{shot_id}")
async def patch_video_plan_shot(
    project_id: str,
    script_id: str,
    shot_id: str,
    body: PatchVideoPlanShotRequest,
    if_match: int | None = Header(None, alias="If-Match"),
):
    """用户编辑单镜字段（镜内多轨结构 patch）。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    from core.edit.video_plan_service import (
        VideoPlanNotFoundError,
        VideoPlanRevisionError,
        patch_shot_plan_fields,
    )
    from core.guards.reference import ScriptEditGuardError

    expected = if_match
    try:
        view = patch_shot_plan_fields(
            state.store,
            script_id,
            shot_id,
            body.model_dump(exclude_unset=True),
            expected_revision=expected,
        )
    except ScriptEditGuardError as exc:
        raise HTTPException(403, str(exc)) from exc
    except VideoPlanRevisionError as exc:
        raise HTTPException(409, str(exc)) from exc
    except VideoPlanNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    from core.store.persist import schedule_save

    schedule_save(state.store, immediate=True)
    return view


@router.post("/projects/{project_id}/scripts/{script_id}/video-plan/ops")
async def post_video_plan_ops(
    project_id: str,
    script_id: str,
    body: VideoPlanOpsRequest,
    if_match: int | None = Header(None, alias="If-Match"),
):
    """用户执行分镜结构性操作（增删/拆分/合并/排序等）。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    from core.edit.video_plan_service import (
        VideoPlanNotFoundError,
        VideoPlanRevisionError,
        apply_video_plan_ops,
    )
    from core.guards.reference import ScriptEditGuardError

    expected = body.expected_revision if body.expected_revision is not None else if_match
    try:
        view = apply_video_plan_ops(
            state.store,
            script_id,
            body.ops,
            expected_revision=expected,
        )
    except ScriptEditGuardError as exc:
        raise HTTPException(403, str(exc)) from exc
    except VideoPlanRevisionError as exc:
        raise HTTPException(409, str(exc)) from exc
    except VideoPlanNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    from core.store.persist import schedule_save

    schedule_save(state.store, immediate=True)
    return view


@router.post("/projects/{project_id}/scripts/{script_id}/video-plan/sync-from-tts")
def sync_video_plan_from_tts(project_id: str, script_id: str):
    """手动从 TTS 同步时长与句级字幕到 VideoPlan.shot_detail。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    from core.edit.shot_detail_sync import sync_plan_from_tts

    try:
        result = sync_plan_from_tts(state.store, script_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    state.persist_store()
    return result


class AvSyncAnalyzeRequest(BaseModel):
    """音画协调分析请求。"""

    mode: str = "analyze_only"
    shot_ids: list[str] | None = None


class AvSyncApplyRequest(BaseModel):
    """应用单条音画协调方案。"""

    action: dict


@router.post("/projects/{project_id}/scripts/{script_id}/video-plan/av-sync")
def analyze_video_plan_av_sync(
    project_id: str,
    script_id: str,
    body: AvSyncAnalyzeRequest | None = None,
):
    """分析（可选应用）音画时长协调方案。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    from core.edit.av_sync import reconcile_script_av

    req = body or AvSyncAnalyzeRequest()
    mode = req.mode if req.mode in ("analyze_only", "hybrid", "auto_only") else "analyze_only"
    persist = mode != "analyze_only"
    try:
        result = reconcile_script_av(
            state.store,
            script_id,
            mode=mode,  # type: ignore[arg-type]
            shot_ids=req.shot_ids,
            persist=persist,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if persist:
        state.persist_store()
    return result


@router.post(
    "/projects/{project_id}/scripts/{script_id}/video-plan/shots/{shot_id}/av-sync/apply"
)
def apply_shot_av_sync_action(
    project_id: str,
    script_id: str,
    shot_id: str,
    body: AvSyncApplyRequest,
):
    """用户选择并应用单镜音画协调方案。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    from core.edit.av_sync.orchestrator import apply_named_sync_action
    from core.guards.reference import ScriptEditGuardError

    try:
        result = apply_named_sync_action(
            state.store, script_id, shot_id, body.action
        )
    except ScriptEditGuardError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    state.persist_store()
    return result


@router.post(
    "/projects/{project_id}/scripts/{script_id}/shots/{shot_id}/subtitles-from-voice"
)
def preview_subtitles_from_voice_audio(
    project_id: str,
    script_id: str,
    shot_id: str,
):
    """从已绑定配音音频生成句级字幕预览（TTS cues / WhisperX ASR，非配音幕文案拆句）。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    from core.edit.shot_detail_sync import build_shot_subtitles_from_voice_audio

    try:
        subtitles = build_shot_subtitles_from_voice_audio(
            state.store, script_id, shot_id
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    state.persist_store()
    return {
        "shot_id": shot_id,
        "count": len(subtitles),
        "subtitles": subtitles,
    }


@router.post("/projects/{project_id}/scripts/{script_id}/shots/{shot_id}/voice-audio")
async def upload_shot_voice_audio(
    project_id: str,
    script_id: str,
    shot_id: str,
    file: UploadFile = File(...),
    clip_id: str | None = Form(None),
    narration_text: str = Form(""),
    bind_clip: bool = Form(True),
):
    """上传镜内配音音频：落盘、生成句级字幕 cue，可选绑定 voice clip 并同步时长。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    raw = await file.read()
    from core.assets.voice_audio_upload import ingest_voice_audio_upload

    try:
        result = ingest_voice_audio_upload(
            state.store,
            project_id=project_id,
            script_id=script_id,
            shot_id=shot_id,
            file_bytes=raw,
            filename=file.filename or "voice.mp3",
            narration_text=narration_text,
            clip_id=clip_id or None,
            bind_clip=bind_clip,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    state.persist_store()
    return result


@router.get("/projects/{project_id}/scripts/{script_id}/media")
def list_media(project_id: str, script_id: str):
    """列出剧本相关数字媒体资产（图片/视频/配音/成片），含可播放 link。"""
    from core.llm.tools.shared.media_list import build_media_item

    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    assets = state.store.list_media_for_script(script_id)
    return [build_media_item(state.store, a) for a in assets]


@router.post("/projects/{project_id}/scripts/{script_id}/conversations")
async def post_conversation(
    project_id: str, script_id: str, body: CreateConversationRequest | None = None
):
    """创建新对话线程并返回 conversation_id。"""
    project = state.store.get_project(project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    title = (body.title if body else "") or "新对话"
    conv = state.conversation_index.create(project_id, script_id, title=title)
    state.conversation_sqlite.upsert_conversation(conv)
    await state.persist_store_async()
    return {
        "conversation_id": conv.id,
        "project_id": conv.project_id,
        "script_id": conv.script_id,
        "created_at": conv.created_at,
    }


@router.get("/projects/{project_id}/conversations")
def list_conversations(project_id: str, script_id: str | None = None):
    """列出项目下历史对话（可按剧本过滤）。"""
    if not state.store.get_project(project_id):
        raise HTTPException(404, "项目不存在")
    if script_id:
        items = state.conversation_index.list_for_project(
            project_id, script_id=script_id
        )
        seen = {c.id for c in items}
        for conv in state.conversation_sqlite.list_conversations(
            project_id, script_id=script_id
        ):
            if conv.id not in seen and state.conversation_index.merge_conversation(conv):
                items.append(conv)
                seen.add(conv.id)
        items.sort(
            key=lambda c: c.updated_at or c.created_at or "",
            reverse=True,
        )
    else:
        state.conversation_index.merge_from_sqlite(state.conversation_sqlite)
        items = state.conversation_index.list_for_project(project_id)
    return [
        {
            "id": c.id,
            "script_id": c.script_id,
            "title": c.title,
            "last_summary": c.last_summary,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
            "status": c.status.value,
            "last_round_token_usage": c.last_round_token_usage,
            "total_token_usage": c.total_token_usage,
        }
        for c in items
    ]


@router.get("/projects/{project_id}/conversations/{conversation_id}/messages")
def get_conversation_messages(
    project_id: str,
    conversation_id: str,
    view: str = "ui",
    limit: int = 80,
    before: str | None = None,
):
    """加载单对话消息；view=ui 为用户可见摘要，view=full 为完整时间线（支持分页）。"""
    load_start = time.perf_counter()
    conv = state.conversation_index.get(conversation_id)
    if not conv:
        conv = state.conversation_sqlite.get_conversation(conversation_id)
        if conv:
            state.conversation_index.merge_conversation(conv)
    if not conv or conv.project_id != project_id:
        raise HTTPException(404, "对话不存在")
    if view == "full":
        if before is not None or limit < 10_000:
            from core.conversation.timeline import build_conversation_timeline_page

            timeline, has_more, oldest_created_at = build_conversation_timeline_page(
                conversation_id,
                state.conversation_sqlite,
                limit=limit,
                before_created_at=before,
                conversation_store=state.conversations,
            )
            log_perf(
                "api.timeline",
                "build_conversation_timeline_page",
                duration_ms=(time.perf_counter() - load_start) * 1000,
                conversation_id=conversation_id,
                view=view,
                timeline_items=len(timeline),
                limit=limit,
                has_more=has_more,
            )
            return {
                "conversation_id": conversation_id,
                "timeline": timeline,
                "has_more": has_more,
                "oldest_created_at": oldest_created_at,
            }
        from core.conversation.timeline import build_conversation_timeline

        timeline = build_conversation_timeline(
            conversation_id,
            state.conversation_sqlite,
            conversation_store=state.conversations,
        )
        log_perf(
            "api.timeline",
            "build_conversation_timeline",
            duration_ms=(time.perf_counter() - load_start) * 1000,
            conversation_id=conversation_id,
            view=view,
            timeline_items=len(timeline),
        )
        return {
            "conversation_id": conversation_id,
            "timeline": timeline,
        }
    msgs = state.conversations.list_master_messages_for_ui(conversation_id)
    log_perf(
        "api.timeline",
        "list_master_messages_for_ui",
        duration_ms=(time.perf_counter() - load_start) * 1000,
        conversation_id=conversation_id,
        view=view,
        message_count=len(msgs),
    )
    return [
        {
            "role": m.role.value,
            "content": m.content,
            "created_at": m.created_at,
        }
        for m in msgs
    ]


@router.get("/projects/{project_id}/scripts/{script_id}/executions/active")
def get_active_execution(project_id: str, script_id: str):
    """查询剧本是否仍有进行中的主编排（含后台 chat 任务）。"""
    from core.execution.cancel import get_execution_cancel_registry

    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    registry = get_execution_cancel_registry()
    active = registry.is_active(script_id) or state.is_chat_running(script_id)
    return {
        "active": active,
        "conversation_id": registry.conversation_id(script_id),
    }


@router.post("/projects/{project_id}/scripts/{script_id}/chat")
async def post_chat(project_id: str, script_id: str, body: ChatRequest):
    """
    用户对话入口：超级视频大师自动规划并调用子 Agent。
    视频风格在首次生成剧本时绑定到 script，之后不可修改。
    """
    project = state.store.get_project(project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")

    if body.generation_mode is not None:
        project.config.generation.mode = body.generation_mode

    execution_override = body.execution_mode

    if not body.message.strip():
        raise HTTPException(400, "消息不能为空")

    # 已锁定风格时，禁止传入不同 style_mode
    if script.style_locked and body.style_mode is not None:
        if script.style_mode and body.style_mode != script.style_mode:
            raise HTTPException(
                400,
                f"剧本视频风格已锁定为 {script.style_mode}，不可修改",
            )

    from core.execution.cancel import get_execution_cancel_registry
    from core.models.entities import ScriptStatus

    registry = get_execution_cancel_registry()
    if (
        script.status == ScriptStatus.EXECUTING
        or registry.is_active(script_id)
        or state.is_chat_running(script_id)
    ):
        raise HTTPException(400, "剧本正在执行中，请稍候")

    try:
        if body.conversation_id:
            state.conversation_index.require(
                body.conversation_id,
                project_id=project_id,
                script_id=script_id,
            )
            conversation_id = body.conversation_id
        else:
            preview = body.message.strip().replace("\n", " ")
            if len(preview) > 48:
                preview = preview[:48] + "…"
            conv = state.conversation_index.create(
                project_id,
                script_id,
                title=preview or "新对话",
            )
            conversation_id = conv.id

        task = asyncio.create_task(
            run_chat_background(
                state,
                project_id=project_id,
                script_id=script_id,
                conversation_id=conversation_id,
                message=body.message,
                requested_style=body.style_mode,
                requested_hints=body.style_hints,
                execution_mode=execution_override,
                skill_id=body.skill_id,
            )
        )
        state.register_chat_task(script_id, task)
    except ScriptStyleLockedError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        msg = str(e)
        if "对话" in msg:
            raise HTTPException(404, msg)
        raise HTTPException(400, msg)

    return JSONResponse(
        status_code=202,
        content={
            "accepted": True,
            "conversation_id": conversation_id,
            "message": "主编排已在后台启动，进度通过 WebSocket 推送。",
        },
    )


@router.post("/projects/{project_id}/scripts/{script_id}/chat/abort")
async def post_chat_abort(project_id: str, script_id: str):
    """用户中止正在进行的超级视频大师主编排。"""
    from core.execution.cancel import get_execution_cancel_registry

    project = state.store.get_project(project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")

    registry = get_execution_cancel_registry()
    if not registry.is_active(script_id):
        raise HTTPException(409, "当前没有正在执行的主编排")

    registry.request_cancel(script_id)
    cancelled_confirmations = state.confirmation_manager.cancel_all_pending()
    conversation_id = registry.conversation_id(script_id)
    await state.emitter.emit(
        {
            "type": "execution_abort_requested",
            "script_id": script_id,
            "project_id": project_id,
            "conversation_id": conversation_id,
            "cancelled_confirmations": cancelled_confirmations,
        }
    )
    return {
        "ok": True,
        "script_id": script_id,
        "conversation_id": conversation_id,
        "cancelled_confirmations": cancelled_confirmations,
    }
