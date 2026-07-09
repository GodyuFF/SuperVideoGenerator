"""剪辑时间轴 REST API。"""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from apps.api.state import state
from core.edit.export_jobs import create_export_job, get_export_job, job_to_dict, run_export_job
from core.edit.export_settings import get_export_manager
from core.edit.ffmpeg_renderer import FfmpegExportError, export_timeline_to_mp4
from core.edit.export_paths import (
    export_filename_for_asset,
    nle_export_filename_for_asset,
    prepare_export_output_path,
)
from core.edit.nle_export import NleExportError, export_timeline_to_premiere_package
from core.edit.edit_capabilities import load_edit_capabilities
from core.edit.timeline_service import (
    TimelineRevisionError,
    get_timeline_for_script,
    patch_timeline,
    validate_timeline_for_script,
)
from core.guards.reference import ScriptEditGuard, ScriptEditGuardError
from core.models.entities import AssetStatus, MediaAsset, MediaAssetType, VideoStyleMode, new_id
from core.store.persist import schedule_save
from core.store.project_paths import export_api_path, sync_script_meta

router = APIRouter(prefix="/api", tags=["edit-timeline"])


class PatchEditTimelineRequest(BaseModel):
    tracks: dict[str, Any] | None = None
    video_layers: list[dict[str, Any]] | None = None
    duration_ms: int | None = None
    metadata: dict[str, Any] | None = None


class AnalyzeEditTimelineRequest(BaseModel):
    """时间段剪辑分析请求体。"""

    start_ms: int | None = None
    end_ms: int | None = None
    tracks: list[str] | None = None
    layer_ids: list[str] | None = None
    include_hints: bool = True
    include_shot_alignment: bool = True


@router.get("/edit/capabilities")
def get_edit_capabilities():
    """剪辑能力枚举（运镜/转场/背景）。"""
    return load_edit_capabilities()


@router.get("/projects/{project_id}/scripts/{script_id}/edit-timeline")
def get_edit_timeline(project_id: str, script_id: str):
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    data = get_timeline_for_script(state.store, script_id)
    if data is None:
        raise HTTPException(404, "剪辑时间轴不存在")
    data["editable"] = ScriptEditGuard.is_editable(script)
    return data


@router.patch("/projects/{project_id}/scripts/{script_id}/edit-timeline")
async def patch_edit_timeline(
    project_id: str,
    script_id: str,
    body: PatchEditTimelineRequest,
    if_match: int | None = Header(None, alias="If-Match"),
):
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    try:
        view = patch_timeline(
            state.store,
            script_id=script_id,
            project_id=project_id,
            body=body.model_dump(exclude_unset=True),
            expected_revision=if_match,
        )
    except ScriptEditGuardError as exc:
        raise HTTPException(403, str(exc)) from exc
    except TimelineRevisionError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    schedule_save(state.store, immediate=True)
    await state.emitter.emit(
        {
            "type": "edit_timeline_updated",
            "script_id": script_id,
            "project_id": project_id,
            "revision": view.get("revision"),
        }
    )
    return view


@router.post("/projects/{project_id}/scripts/{script_id}/edit-timeline/validate")
def post_validate_edit_timeline(project_id: str, script_id: str):
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    return validate_timeline_for_script(state.store, script_id)


@router.post("/projects/{project_id}/scripts/{script_id}/edit-timeline/analyze")
def post_analyze_edit_timeline(
    project_id: str,
    script_id: str,
    body: AnalyzeEditTimelineRequest | None = None,
):
    """按时间窗分析剪辑结构、空白、重叠与优化建议。"""
    from core.edit.timeline_analysis import AnalyzeTimelineRequest, analyze_edit_timeline

    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    timeline = state.store.get_edit_timeline_for_script(script_id)
    if timeline is None:
        raise HTTPException(404, "剪辑时间轴不存在")
    req_body = body or AnalyzeEditTimelineRequest()
    request = AnalyzeTimelineRequest(
        start_ms=req_body.start_ms,
        end_ms=req_body.end_ms,
        tracks=req_body.tracks,
        layer_ids=req_body.layer_ids,
        include_hints=req_body.include_hints,
        include_shot_alignment=req_body.include_shot_alignment,
    )
    result = analyze_edit_timeline(state.store, timeline, request)
    return result.to_dict()


def _run_export_worker(job_id: str, project_id: str, script_id: str) -> dict[str, Any]:
    timeline = state.store.get_edit_timeline_for_script(script_id)
    if timeline is None:
        raise FfmpegExportError("剪辑时间轴不存在")

    script = state.store.get_script(script_id)
    style_mode = script.style_mode if script else VideoStyleMode.DYNAMIC_IMAGE
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
    url = export_api_path(project_id, script_id, export_name)
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
    sync_script_meta(state.store, project_id, script_id)
    schedule_save(state.store, immediate=True)
    return {
        "asset_id": fin_id,
        "url": url,
        "duration_ms": result.duration_ms,
        "segment_count": result.segment_count,
    }


def _run_nle_export_worker(project_id: str, script_id: str) -> dict[str, Any]:
    """后台任务：导出 Premiere FCP7 XMEML 工程 ZIP。"""
    timeline = state.store.get_edit_timeline_for_script(script_id)
    if timeline is None:
        raise NleExportError("剪辑时间轴不存在")

    script = state.store.get_script(script_id)
    pkg_id = new_id("media")
    out_path = prepare_export_output_path(project_id, script_id, pkg_id)
    out_path = out_path.with_name(nle_export_filename_for_asset(pkg_id))

    result = export_timeline_to_premiere_package(
        state.store,
        timeline,
        out_path,
        project_id=project_id,
        script_id=script_id,
        sequence_name=script.title if script else script_id,
        manager=get_export_manager(),
    )
    export_name = nle_export_filename_for_asset(pkg_id)
    url = export_api_path(project_id, script_id, export_name)
    media = MediaAsset(
        id=pkg_id,
        project_id=project_id,
        script_id=script_id,
        type=MediaAssetType.FINAL,
        name="nle_premiere_package",
        url=url,
        status=AssetStatus.GENERATED,
        metadata={
            "render": "nle_premiere",
            "format": result.format,
            "duration_ms": result.duration_ms,
            "media_count": result.media_count,
            "clip_count": result.clip_count,
            "local_path": str(result.output_path),
        },
    )
    state.store.add_media_asset(media)
    sync_script_meta(state.store, project_id, script_id)
    schedule_save(state.store, immediate=True)
    return {
        "asset_id": pkg_id,
        "url": url,
        "duration_ms": result.duration_ms,
        "media_count": result.media_count,
        "clip_count": result.clip_count,
        "format": result.format,
    }


@router.post("/projects/{project_id}/scripts/{script_id}/export-nle")
async def post_export_nle_timeline(project_id: str, script_id: str):
    """异步导出 Premiere Pro 工程包（FCP7 XMEML ZIP）。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")

    job = create_export_job(project_id, script_id)
    job_id = job.id

    async def _notify_progress(payload: dict[str, Any]) -> None:
        await state.broadcast(project_id, script_id, payload)

    def worker(_job):
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                _notify_progress(
                    {
                        "type": "export_nle_progress",
                        "script_id": script_id,
                        "job_id": job_id,
                        "status": "running",
                        "progress": 0.5,
                    }
                )
            )
            loop.close()
        except Exception:
            pass
        return _run_nle_export_worker(project_id, script_id)

    threading.Thread(target=lambda: run_export_job(job_id, worker), daemon=True).start()
    return {"ok": True, "job_id": job_id}


@router.get("/projects/{project_id}/scripts/{script_id}/export-nle/{job_id}")
def get_export_nle_job_status(project_id: str, script_id: str, job_id: str):
    """查询 NLE 工程导出任务状态。"""
    job = get_export_job(job_id)
    if job is None or job.project_id != project_id or job.script_id != script_id:
        raise HTTPException(404, "导出任务不存在")
    return job_to_dict(job)


@router.post("/projects/{project_id}/scripts/{script_id}/export")
async def post_export_timeline(project_id: str, script_id: str):
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")

    job = create_export_job(project_id, script_id)
    job_id = job.id

    async def _notify_progress(payload: dict[str, Any]) -> None:
        await state.broadcast(project_id, script_id, payload)

    def worker(_job):
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                _notify_progress(
                    {
                        "type": "export_progress",
                        "script_id": script_id,
                        "job_id": job_id,
                        "status": "running",
                        "progress": 0.5,
                    }
                )
            )
            loop.close()
        except Exception:
            pass
        return _run_export_worker(job_id, project_id, script_id)

    threading.Thread(target=lambda: run_export_job(job_id, worker), daemon=True).start()
    return {"ok": True, "job_id": job_id}


@router.get("/projects/{project_id}/scripts/{script_id}/export/{job_id}")
def get_export_job_status(project_id: str, script_id: str, job_id: str):
    job = get_export_job(job_id)
    if job is None or job.project_id != project_id or job.script_id != script_id:
        raise HTTPException(404, "导出任务不存在")
    return job_to_dict(job)
