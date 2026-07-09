"""REST API：项目、剧本、配置、Plan/Execute。"""

from pathlib import PurePath

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from apps.api.state import create_project, create_script, delete_project, delete_projects_batch, delete_script, state
from core.guards.script_style import ScriptStyleLockedError
from core.models.entities import GenerationMode, ExecutionMode, ImageSourceMode, VideoStyleMode
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
}


class CreateProjectRequest(BaseModel):
    """创建项目请求体。"""

    title: str


class CreateScriptRequest(BaseModel):
    """创建剧本请求体。"""

    title: str
    duration_sec: int = 60
    style_mode: VideoStyleMode | None = None  # 若提供则在创建时绑定并锁定风格


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
    style_mode: VideoStyleMode | None = None
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
                    {"id": s.id, "title": s.title, "status": s.status.value}
                    for s in scripts
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
    rel = project_paths.relative_media_path(project_id, script_id, filename)
    path = absolute_media_path(rel)
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
    """列出剧本相关资产（含共享池）；type 可过滤 character/prop/scene/frame/plot/narration。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    assets = state.store.list_assets_for_script(script_id)
    if type:
        assets = [a for a in assets if a.type.value == type]
    return [a.model_dump() for a in assets]


@router.post("/projects/{project_id}/scripts/{script_id}/assets/reapply-chroma")
def reapply_chroma_for_script_assets(
    project_id: str,
    script_id: str,
    force: bool = False,
):
    """对 character/prop 关联图片重新绿幕抠图（修复未抠图的历史资产）。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    from core.assets.chroma_key import reapply_chroma_for_script
    from core.store.persist import schedule_save

    result = reapply_chroma_for_script(
        state.store,
        project_id=project_id,
        script_id=script_id,
        force=force,
    )
    schedule_save(state.store, immediate=True)
    return result


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
    state.persist_store()
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
    """用户手动创建剧情/角色/场景/物品资产。"""
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
    state.persist_store()
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
    from core.assets.user_crud import user_delete_text_asset
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
    except ScriptEditGuardError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    state.persist_store()
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
    state.persist_store()
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


@router.get("/projects/{project_id}/scripts/{script_id}/plan")
def get_plan(project_id: str, script_id: str):
    """获取当前 PlanDocument。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    plan = state.store.get_plan(script_id)
    if not plan:
        raise HTTPException(404, "计划不存在")
    return plan.model_dump()


@router.get("/projects/{project_id}/scripts/{script_id}/video-plan")
def get_video_plan(project_id: str, script_id: str):
    """获取分镜视频计划稿（镜头列表与旁白）。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    vp = state.store.get_video_plan_for_script(script_id)
    if not vp:
        raise HTTPException(404, "视频计划稿不存在")
    from core.edit.shot_timing import resolve_shot_timings

    payload = vp.model_dump()
    payload["shot_timings"] = [t.to_dict() for t in resolve_shot_timings(state.store, script_id, plan=vp)]
    return payload


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
def post_conversation(
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
    state.persist_store()
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
    state.conversation_index.merge_from_sqlite(state.conversation_sqlite)
    items = state.conversation_index.list_for_project(
        project_id, script_id=script_id
    )
    if script_id:
        seen = {c.id for c in items}
        for conv in state.conversation_sqlite.list_conversations(
            project_id, script_id=script_id
        ):
            if conv.id not in seen:
                state.conversation_index.merge_conversation(conv)
                items.append(conv)
                seen.add(conv.id)
        items.sort(
            key=lambda c: c.updated_at or c.created_at or "",
            reverse=True,
        )
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
):
    """加载单对话消息；view=ui 为用户可见摘要，view=full 为完整时间线。"""
    conv = state.conversation_index.get(conversation_id)
    if not conv:
        conv = state.conversation_sqlite.get_conversation(conversation_id)
        if conv:
            state.conversation_index.merge_conversation(conv)
    if not conv or conv.project_id != project_id:
        raise HTTPException(404, "对话不存在")
    if view == "full":
        from core.conversation.timeline import build_conversation_timeline

        timeline = build_conversation_timeline(
            conversation_id, state.conversation_sqlite
        )
        return {
            "conversation_id": conversation_id,
            "timeline": timeline,
        }
    msgs = state.conversations.list_master_messages_for_ui(conversation_id)
    return [
        {
            "role": m.role.value,
            "content": m.content,
            "created_at": m.created_at,
        }
        for m in msgs
    ]


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
                f"剧本视频风格已锁定为 {script.style_mode.value}，不可修改",
            )

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

        conversation_id, summary = await state.super_video_master.run_from_message(
            project_id,
            script_id,
            body.message,
            requested_style=body.style_mode,
            conversation_id=conversation_id,
            execution_mode=execution_override,
            skill_id=body.skill_id,
        )
    except ScriptStyleLockedError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        msg = str(e)
        if "对话" in msg:
            raise HTTPException(404, msg)
        raise HTTPException(400, msg)
    except RuntimeError as e:
        raise HTTPException(502, str(e))

    state.persist_store()

    script = state.store.get_script(script_id)
    plan = state.store.get_plan(script_id)
    conv = state.conversation_index.get(conversation_id)
    return {
        "conversation_id": conversation_id,
        "summary": summary,
        "token_usage": conv.last_round_token_usage if conv else {},
        "script": script.model_dump() if script else None,
        "plan": plan.model_dump() if plan else None,
    }


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
