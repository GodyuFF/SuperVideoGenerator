"""生成队列单条任务执行器。"""
from __future__ import annotations

from typing import Any

from core.assets.regenerate import (
    RegenerateError,
    VideoRegenerateOptions,
    _regenerate_shot_video,
    build_regenerate_context,
    regenerate_asset,
)
from core.events.emitter import EventEmitter
from core.generation.models import GenerationJob
from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.image.generate import generate_one_image_item
from core.llm.tools.video.shot_spec import ShotVideoGenSpec, resolve_video_clip_gen_spec
from core.llm.tools.video.generate import generate_one_shot_video
from core.llm.tools.video.video_clips import generate_one_video_clip
from core.store.memory import MemoryStore


def _build_agent_context(
    store: MemoryStore,
    emitter: EventEmitter | None,
    job: GenerationJob,
    *,
    parent_ctx: AgentRunContext | None = None,
) -> AgentRunContext:
    """为 Agent/批处理 payload 路径构造最小运行上下文。"""
    ctx = build_regenerate_context(
        store=store,
        emitter=emitter,
        project_id=job.project_id,
        script_id=job.script_id,
        agent_name=job.source,
    )
    if parent_ctx is not None:
        ctx.outputs = parent_ctx.outputs
        ctx.step_id = parent_ctx.step_id
        ctx.agent_name = parent_ctx.agent_name
        ctx.task_brief = parent_ctx.task_brief
        ctx.work_context = parent_ctx.work_context
    return ctx


def _is_image_payload(payload: dict[str, Any]) -> bool:
    """判断 payload 是否为单条生图 item。"""
    return bool(payload.get("source_text_asset_id"))


def _video_spec_from_payload(
    store: MemoryStore,
    payload: dict[str, Any],
) -> ShotVideoGenSpec:
    """从队列 payload 还原视频片段生成规格。"""
    clip_id = str(payload.get("video_clip_asset_id", "")).strip()
    if clip_id and not str(payload.get("prompt", "")).strip():
        return resolve_video_clip_gen_spec(
            store,
            clip_id,
            shot_id=str(payload.get("shot_id", "")),
            order=int(payload.get("order", 0)),
            sub_shot_idx=int(payload.get("sub_shot_idx", 0)),
            duration_sec=payload.get("duration_sec"),
            forced_video_mode=payload.get("forced_video_mode"),
            allowed_modes=payload.get("allowed_modes"),
        )
    return ShotVideoGenSpec(
        shot_id=str(payload.get("shot_id", "")),
        order=int(payload.get("order", 0)),
        mode=payload.get("mode", "text2video"),  # type: ignore[arg-type]
        prompt=str(payload.get("prompt", "")),
        image_url=payload.get("image_url"),
        keyframe_urls=list(payload.get("keyframe_urls") or []),
        duration_sec=float(payload.get("duration_sec", 5.0)),
        sub_shot_idx=int(payload.get("sub_shot_idx", 0)),
        source_frame_asset_id=str(payload.get("source_frame_asset_id", "")),
        source_frame_asset_ids=list(payload.get("source_frame_asset_ids") or []),
        source_media_ids=list(payload.get("source_media_ids") or []),
        video_clip_asset_id=clip_id,
    )


async def run_generation_job(
    store: MemoryStore,
    emitter: EventEmitter | None,
    job: GenerationJob,
    *,
    parent_ctx: AgentRunContext | None = None,
) -> None:
    """按任务类型执行单条图片或视频生成。"""
    if job.payload is not None:
        ctx = _build_agent_context(store, emitter, job, parent_ctx=parent_ctx)
        if job.payload.get("regenerate_shot_video"):
            shot_id = str(job.payload.get("shot_id") or job.asset_id).strip()
            if not shot_id:
                raise RegenerateError("分镜视频二次生成缺少 shot_id")
            video_options = VideoRegenerateOptions.from_payload(job.payload)
            result = await _regenerate_shot_video(
                store,
                ctx,
                shot_id,
                video_options=video_options,
            )
            if not result.ok:
                raise RegenerateError(result.message or "分镜视频二次生成失败")
            return
        if job.kind == "image" or _is_image_payload(job.payload):
            await generate_one_image_item(store, ctx, job.payload)
            return
        if job.kind == "video":
            spec = _video_spec_from_payload(store, job.payload)
            if job.payload.get("shot_video"):
                await generate_one_shot_video(store, ctx, spec)
            else:
                await generate_one_video_clip(store, ctx, spec)
            return
        raise ValueError(f"无法识别的生成 payload：kind={job.kind}")

    result = await regenerate_asset(
        store,
        emitter,
        project_id=job.project_id,
        script_id=job.script_id,
        asset_id=job.asset_id,
        variant_id=job.variant_id,
    )
    if not result.ok:
        raise RegenerateError(result.message or "二次生成失败")
