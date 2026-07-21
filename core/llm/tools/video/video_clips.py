"""generate_video_clips：按 video_clip 文字资产生成 AI 视频。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.execution.cancel import check_cancelled
from core.llm.agent.react_core import AgentRunContext, StepOutput
from core.llm.style.video_capability import script_style_video_modes
from core.llm.tools.video.agnes_client import AgnesVideoGenerationError
from core.llm.tools.video.ark_client import ArkVideoGenerationError
from core.llm.tools.video.provider import generate_video_async
from core.llm.tools.video.generate import is_video_gen_available
from core.llm.tools.video.settings import get_video_gen_manager
from core.llm.tools.video.frame_i2v_spec import resolve_frame_i2v_clip_spec
from core.llm.tools.video.shot_spec import ShotVideoGenSpec, resolve_video_clip_gen_spec
from core.models.entities import MediaAssetType, TextAssetType, new_id
from core.store.memory import MemoryStore
from core.store.persist import schedule_save

logger = logging.getLogger("core.llm.tools.video.video_clips")


def collect_video_clip_specs(
    store: MemoryStore,
    script_id: str,
    args: dict[str, Any],
) -> list[ShotVideoGenSpec]:
    """收集待生成的 video_clip 规格列表。"""
    from core.guards.script_style import normalize_style_mode_id
    from core.llm.master.actions import uses_frame_i2v_pipeline

    raw_ids = args.get("asset_ids") or args.get("video_clip_asset_ids") or []
    if not isinstance(raw_ids, list):
        raw_ids = []
    allowed = args.get("allowed_video_modes")
    if allowed is None:
        allowed = script_style_video_modes(store, script_id)
    forced_mode = str(args.get("video_mode") or "").strip() or None
    script = store.get_script(script_id)
    style_id = normalize_style_mode_id(script.style_mode if script else None)
    use_frame_i2v = uses_frame_i2v_pipeline(style_id or "")
    specs: list[ShotVideoGenSpec] = []
    if raw_ids:
        ids = [str(x).strip() for x in raw_ids if str(x).strip()]
    else:
        ids = [
            a.id
            for a in store.text_assets.values()
            if a.type == TextAssetType.VIDEO_CLIP
            and (a.source_script_id == script_id or a.script_id == script_id)
        ]
    for aid in ids:
        try:
            if use_frame_i2v:
                specs.append(
                    resolve_frame_i2v_clip_spec(
                        store,
                        script_id,
                        aid,
                        forced_video_mode=forced_mode,
                        allowed_modes=allowed,
                    )
                )
            else:
                specs.append(
                    resolve_video_clip_gen_spec(
                        store,
                        aid,
                        forced_video_mode=forced_mode,
                        allowed_modes=allowed,
                    )
                )
        except ValueError as e:
            logger.warning("跳过 video_clip %s：%s", aid, e)
    return specs


def _persist_video_clip_media(
    store: MemoryStore,
    ctx: AgentRunContext,
    *,
    spec: ShotVideoGenSpec,
    url: str,
    task_meta: dict[str, Any],
) -> dict[str, Any]:
    """落盘 video_clip 生成的视频并回填文字资产 primary_media_id。"""
    from core.edit.shot_media_bind import bind_video_clip_media_to_plan
    from core.llm.agent.llm_action import _persist_media

    project_id = str(ctx.work_context.get("project_id") or ctx.project_id or "")
    script_id = ctx.script_id
    clip_id = spec.video_clip_asset_id or spec.shot_id
    label = f"video_clip_{clip_id[-8:]}"
    media_id = new_id("media")
    metadata = {
        "video_mode": spec.mode,
        "video_clip_asset_id": spec.video_clip_asset_id,
        "provider_task_id": task_meta.get("task_id") or task_meta.get("id"),
        "provider": task_meta.get("provider") or get_video_gen_manager().get_settings().provider,
    }
    if spec.shot_id and not spec.shot_id.startswith("txt_"):
        metadata["shot_id"] = spec.shot_id
    _persist_media(
        store,
        project_id=project_id,
        script_id=script_id,
        media_type=MediaAssetType.VIDEO,
        name=label,
        url=url,
        asset_id=media_id,
        metadata=metadata,
        source_asset_id=spec.video_clip_asset_id or None,
    )
    asset = store.get_text_asset(spec.video_clip_asset_id)
    if asset:
        asset.primary_media_id = media_id
        store.update_text_asset(asset)
    if spec.video_clip_asset_id:
        bind_video_clip_media_to_plan(
            store,
            script_id,
            spec.video_clip_asset_id,
            media_id,
            sub_shot_idx=spec.sub_shot_idx,
        )
    ctx.outputs.append(
        StepOutput(
            kind="video",
            label=label,
            asset_id=media_id,
            url=url,
        )
    )
    return {
        "video_clip_asset_id": spec.video_clip_asset_id,
        "shot_id": spec.shot_id,
        "url": url,
        "asset_id": media_id,
        "label": label,
        "mode": spec.mode,
        "duration_ms": int(spec.duration_sec * 1000),
    }


async def _generate_one_clip(
    store: MemoryStore,
    ctx: AgentRunContext,
    spec: ShotVideoGenSpec,
    *,
    semaphore: asyncio.Semaphore,
) -> tuple[dict[str, Any] | None, str | None]:
    """并发生成单个 video_clip。"""
    async with semaphore:
        check_cancelled(ctx.script_id)
        try:
            url, meta = await generate_video_async(
                prompt=spec.prompt,
                mode=spec.mode,
                image_url=spec.image_url,
                keyframe_urls=spec.keyframe_urls or None,
                duration_sec=spec.duration_sec,
            )
            clip = _persist_video_clip_media(store, ctx, spec=spec, url=url, task_meta=meta)
            return clip, None
        except (AgnesVideoGenerationError, ArkVideoGenerationError) as e:
            return None, f"video_clip {spec.video_clip_asset_id}：{e}"
        except ValueError as e:
            return None, f"video_clip {spec.video_clip_asset_id}：{e}"


async def run_concurrent_video_clip_generation(
    store: MemoryStore,
    script_id: str,
    args: dict[str, Any],
    ctx: AgentRunContext,
) -> tuple[dict[str, Any], list[str]]:
    """为 video_clip 文字资产经全局队列串行生成视频。"""
    from core.generation.bridge import (
        ensure_generation_runner,
        enqueue_and_wait_video_clip_specs,
        format_video_queue_observation,
        resolve_project_id,
        video_jobs_to_results,
    )

    if not is_video_gen_available():
        return args, ["AI 视频生成未启用或缺少 API Key"]

    allowed = script_style_video_modes(store, script_id)
    if not allowed:
        return args, ["当前视频风格未配置 AI 生视频能力（video）"]

    merged = dict(args)
    merged.setdefault("allowed_video_modes", allowed)
    specs = collect_video_clip_specs(store, script_id, merged)
    if not specs:
        return args, ["未找到可生成的 video_clip 资产"]

    project_id = resolve_project_id(store, ctx, script_id)
    emitter = ctx.work_context.get("emitter")
    ensure_generation_runner(store, emitter, ctx)

    jobs = await enqueue_and_wait_video_clip_specs(
        project_id=project_id,
        script_id=script_id,
        specs=specs,
        source="agent",
    )
    clips, errors = video_jobs_to_results(store, specs, jobs, shot_video=False)

    if not clips and errors:
        return args, errors

    merged = dict(args)
    merged["clips"] = clips
    schedule_save(store, immediate=True)
    if not str(merged.get("observation", "")).strip():
        succeeded = len(clips)
        failed = len(errors)
        merged["observation"] = format_video_queue_observation(
            len(specs),
            succeeded,
            failed,
        )
    return merged, errors


async def generate_one_video_clip(
    store: MemoryStore,
    ctx: AgentRunContext,
    spec: ShotVideoGenSpec,
) -> None:
    """供生成队列串行调用的单条 video_clip 生成入口。"""
    from core.interaction_log.media_log import media_log_scope

    semaphore = asyncio.Semaphore(1)
    with media_log_scope(
        project_id=str(ctx.project_id or ctx.work_context.get("project_id") or ""),
        script_id=str(ctx.script_id or ""),
        agent_name=str(ctx.agent_name or ""),
        step_id=str(ctx.step_id or ""),
        asset_id=str(spec.video_clip_asset_id or spec.shot_id or ""),
    ):
        _clip, err = await _generate_one_clip(store, ctx, spec, semaphore=semaphore)
    if err:
        raise RuntimeError(err)
