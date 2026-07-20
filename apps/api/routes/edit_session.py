"""编辑会话 API：Agent ↔ 编辑器数据桥。

提供 Agent 工具与编辑器之间的数据通道：
- GET  获取编辑会话状态（时间轴、媒体资产）
- PATCH Agent 更新编辑状态（添加片段、调整参数等）
- POST  触发导出
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apps.api.state import state
from core.guards.script_style import normalize_style_mode_id
from core.edit.timeline import (
    build_tts_by_shot,
    resolve_shot_image_ref,
    timeline_board_items,
    timeline_duration_ms,
)
from core.edit.export_jobs import create_export_job, get_export_job, run_export_job
from core.llm.tools.shared.media_list import resolve_media_access
from core.models.entities import MediaAssetType
from core.store.memory import MemoryStore
from core.store.persist import schedule_save

router = APIRouter(prefix="/api", tags=["edit-session"])


class EditSessionPatch(BaseModel):
    """Agent 编辑操作请求体。"""

    action: str = ""  # add_clip, update_clip, remove_clip, set_keyframe, apply_effect
    params: dict[str, Any] = {}


def _build_media_items(store: MemoryStore, script_id: str) -> list[dict[str, Any]]:
    """构建媒体资产列表（供编辑器使用）。"""
    items: list[dict[str, Any]] = []
    for media in store.list_media_for_script(script_id):
        access = resolve_media_access(media.url)
        items.append(
            {
                "id": media.id,
                "name": media.name,
                "type": media.type.value,
                "url": access.get("link", media.url),
                "is_accessible": access.get("is_accessible", False),
                "duration_ms": media.metadata.get("duration_ms"),
                "source_asset_id": media.source_asset_id,
            }
        )
    return items


def _build_timeline_payload(
    store: MemoryStore, script_id: str
) -> dict[str, Any] | None:
    """从存储构建时间轴载荷。"""
    timeline = store.get_edit_timeline_for_script(script_id)
    if timeline is None:
        plan = store.get_video_plan_for_script(script_id)
        if plan is None or not plan.shots:
            return None
        from core.edit.timeline import compile_timeline_from_shots

        timeline = compile_timeline_from_shots(store, script_id=script_id, plan=plan)

    board = timeline_board_items(store, timeline)
    return {
        "source": "edit_timeline",
        "duration_ms": board.get("duration_ms", timeline_duration_ms(timeline)),
        "tracks": board.get("tracks", {}),
        "video_layers": [
            {
                "id": layer.id,
                "name": layer.name,
                "z_index": layer.z_index,
                "clips": [
                    {
                        "id": clip.id,
                        "start_ms": clip.start_ms,
                        "end_ms": clip.end_ms,
                        "label": clip.label,
                        "asset_ref": clip.asset_ref,
                        "transform": clip.transform,
                        "metadata": clip.metadata,
                    }
                    for clip in layer.clips
                ],
            }
            for layer in timeline.video_layers
        ],
        "revision": timeline.revision,
    }


@router.get("/projects/{project_id}/scripts/{script_id}/edit-session")
def get_edit_session(project_id: str, script_id: str):
    """获取编辑会话完整状态。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")

    timeline = _build_timeline_payload(state.store, script_id)
    media = _build_media_items(state.store, script_id)

    return {
        "project_id": project_id,
        "script_id": script_id,
        "script_title": script.title,
        "style_mode": normalize_style_mode_id(script.style_mode) if script.style_mode else "storybook",
        "timeline": timeline,
        "media_assets": media,
    }


@router.patch("/projects/{project_id}/scripts/{script_id}/edit-session")
async def patch_edit_session(
    project_id: str,
    script_id: str,
    body: EditSessionPatch,
):
    """Agent 更新编辑会话状态。

    当前为桥接模式：操作的详细实现将在 Phase 3 Agent Tools 中完成。
    此端点记录操作日志并返回当前状态作为确认。
    """
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")

    # 记录操作（供调试与审计）
    from core.logging.setup import get_logger

    logger = get_logger("edit_session")
    logger.info(
        "edit_session_patch",
        project_id=project_id,
        script_id=script_id,
        action=body.action,
        params=body.params,
    )

    # 返回当前状态
    timeline = _build_timeline_payload(state.store, script_id)
    media = _build_media_items(state.store, script_id)

    return {
        "ok": True,
        "action": body.action,
        "project_id": project_id,
        "script_id": script_id,
        "timeline": timeline,
        "media_assets": media,
    }


@router.post("/projects/{project_id}/scripts/{script_id}/edit-session/export")
async def post_edit_export(project_id: str, script_id: str):
    """触发编辑会话导出。"""
    from core.edit.export_settings import CLASSIC_EXPORT_ONLY_MESSAGE, get_export_manager

    if not get_export_manager().is_ffmpeg_export_enabled():
        raise HTTPException(status_code=403, detail=CLASSIC_EXPORT_ONLY_MESSAGE)

    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")

    from core.edit.export_paths import export_filename_for_asset, prepare_export_output_path
    from core.edit.ffmpeg_renderer import export_timeline_to_mp4
    from core.edit.export_settings import get_export_manager
    from core.models.entities import AssetStatus, MediaAsset, MediaAssetType, VideoStyleMode, new_id

    timeline = state.store.get_edit_timeline_for_script(script_id)
    if timeline is None:
        raise HTTPException(400, "尚无编辑时间轴")

    job = create_export_job(project_id, script_id)
    job_id = job.id

    import threading

    def worker(_job):
        style_mode = script.style_mode or VideoStyleMode.STORYBOOK
        fin_id = new_id("media")
        out_path = prepare_export_output_path(project_id, script_id, fin_id)
        result = export_timeline_to_mp4(
            state.store,
            timeline,
            out_path,
            project_id=project_id,
            script_id=script_id,
            style_mode=style_mode,
            manager=get_export_manager(),
        )
        export_name = export_filename_for_asset(fin_id)
        url = f"/api/projects/{project_id}/scripts/{script_id}/exports/{export_name}"
        media = MediaAsset(
            id=fin_id,
            project_id=project_id,
            script_id=script_id,
            type=MediaAssetType.FINAL,
            name="final_video",
            url=url,
            status=AssetStatus.GENERATED,
            metadata={
                "render": "ffmpeg",
                "duration_ms": result.duration_ms,
                "segment_count": result.segment_count,
                "local_path": str(result.output_path),
            },
        )
        state.store.add_media_asset(media)
        schedule_save(state.store, immediate=True)
        return {"asset_id": fin_id, "url": url, "duration_ms": result.duration_ms}

    threading.Thread(
        target=lambda: run_export_job(job_id, worker), daemon=True
    ).start()

    return {"ok": True, "job_id": job_id}


@router.get("/projects/{project_id}/scripts/{script_id}/edit-session/export/{job_id}")
def get_edit_export_status(project_id: str, script_id: str, job_id: str):
    """查询导出进度。"""
    from core.edit.export_jobs import job_to_dict

    job = get_export_job(job_id)
    if job is None or job.project_id != project_id or job.script_id != script_id:
        raise HTTPException(404, "导出任务不存在")
    return job_to_dict(job)


@router.get("/projects/{project_id}/scripts/{script_id}/media")
def get_script_media(project_id: str, script_id: str):
    """获取剧本关联的媒体资产列表（供编辑器媒体库使用）。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    return _build_media_items(state.store, script_id)
