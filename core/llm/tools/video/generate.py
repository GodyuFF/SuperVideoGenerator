"""generate_clips：收集待生成镜头并调用 Agnes Video V2.0 API。"""

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
from core.llm.tools.video.settings import get_video_gen_manager
from core.llm.tools.video.shot_spec import ShotVideoGenSpec, resolve_shot_video_gen_spec
from core.models.entities import MediaAssetType, new_id
from core.store.memory import MemoryStore
from core.store.persist import schedule_save

logger = logging.getLogger("core.llm.tools.video.generate")


def is_video_gen_available() -> bool:
    """视频生成是否已启用且配置了 API Key。"""
    return get_video_gen_manager().is_available()


def collect_shot_video_specs(
    store: MemoryStore,
    script_id: str,
    args: dict[str, Any],
) -> list[ShotVideoGenSpec]:
    """从 VideoPlan 或 args.shot_ids 收集待生成视频的镜头规格。"""
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return []

    raw_ids = args.get("shot_ids")
    if isinstance(raw_ids, list) and raw_ids:
        wanted = {str(x).strip() for x in raw_ids if str(x).strip()}
        shots = [s for s in plan.shots if s.id in wanted]
    else:
        shots = list(plan.shots)

    sub_idx = int(args.get("sub_shot_idx", 0) or 0)
    preferred_frame = str(args.get("source_frame_asset_id", "") or "").strip()
    raw_frame_ids = args.get("source_frame_asset_ids")
    frame_ids = (
        [str(x).strip() for x in raw_frame_ids if str(x).strip()]
        if isinstance(raw_frame_ids, list)
        else None
    )
    raw_media_ids = args.get("source_media_ids")
    media_ids = (
        [str(x).strip() for x in raw_media_ids if str(x).strip()]
        if isinstance(raw_media_ids, list)
        else None
    )
    element_refs = args.get("source_element_refs")
    if element_refs is not None and not isinstance(element_refs, dict):
        element_refs = None
    forced_mode = str(args.get("video_mode", "") or "").strip() or None
    allowed_modes = args.get("allowed_video_modes")
    if allowed_modes is None:
        allowed_modes = script_style_video_modes(store, script_id)
    elif not isinstance(allowed_modes, list):
        allowed_modes = script_style_video_modes(store, script_id)
    specs: list[ShotVideoGenSpec] = []
    for shot in shots:
        try:
            spec = resolve_shot_video_gen_spec(
                store,
                shot,
                script_id=script_id,
                sub_shot_idx=sub_idx,
                preferred_frame_asset_id=preferred_frame,
                source_frame_asset_ids=frame_ids,
                source_media_ids=media_ids,
                source_element_refs=element_refs,
                forced_video_mode=forced_mode,
                allowed_modes=allowed_modes,
            )
        except ValueError as e:
            logger.warning("跳过镜头 %s：%s", shot.id, e)
            continue
        specs.append(spec)
    return specs


def _persist_generated_video(
    store: MemoryStore,
    ctx: AgentRunContext,
    *,
    spec: ShotVideoGenSpec,
    url: str,
    task_meta: dict[str, Any],
) -> dict[str, Any]:
    """下载远程视频并落盘，返回 generate_clips clip 条目。"""
    from core.llm.agent.llm_action import _persist_media

    project_id = str(ctx.work_context.get("project_id") or ctx.project_id or "")
    script_id = ctx.script_id
    label = f"shot_{spec.order + 1}_video"
    media_id = new_id("media")
    metadata = {
        "shot_id": spec.shot_id,
        "video_mode": spec.mode,
        "agnes_video_id": task_meta.get("video_id"),
        "agnes_task_id": task_meta.get("task_id") or task_meta.get("id"),
        "source_frame_asset_id": spec.source_frame_asset_id,
        "source_frame_asset_ids": spec.source_frame_asset_ids,
        "source_media_ids": spec.source_media_ids,
    }
    _persist_media(
        store,
        project_id=project_id,
        script_id=script_id,
        media_type=MediaAssetType.VIDEO,
        name=label,
        url=url,
        asset_id=media_id,
        metadata=metadata,
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
        "shot_id": spec.shot_id,
        "url": url,
        "asset_id": media_id,
        "label": label,
        "mode": spec.mode,
        "duration_ms": int(spec.duration_sec * 1000),
    }


async def _generate_one_shot(
    store: MemoryStore,
    ctx: AgentRunContext,
    spec: ShotVideoGenSpec,
    *,
    semaphore: asyncio.Semaphore,
) -> tuple[dict[str, Any] | None, str | None]:
    """并发生成单镜视频，返回 (clip_dict, error_message)。"""
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
            clip = _persist_generated_video(store, ctx, spec=spec, url=url, task_meta=meta)
            return clip, None
        except (AgnesVideoGenerationError, ArkVideoGenerationError) as e:
            return None, f"镜头 {spec.shot_id}：{e}"
        except ValueError as e:
            return None, f"镜头 {spec.shot_id}：{e}"


async def run_concurrent_video_generation(
    store: MemoryStore,
    script_id: str,
    args: dict[str, Any],
    ctx: AgentRunContext,
) -> tuple[dict[str, Any], list[str]]:
    """为计划稿镜头经全局队列串行生成视频，写入 clips 供 apply_action_result 绑定。"""
    from core.generation.bridge import (
        ensure_generation_runner,
        enqueue_and_wait_shot_video_specs,
        format_video_queue_observation,
        resolve_project_id,
        video_jobs_to_results,
    )

    if not is_video_gen_available():
        return args, ["AI 视频生成未启用或缺少 API Key"]

    allowed = script_style_video_modes(store, script_id)
    if not allowed:
        return args, ["当前视频风格未配置 AI 生视频能力（video），无法生成视频"]

    merged_args = dict(args)
    merged_args.setdefault("allowed_video_modes", allowed)
    specs = collect_shot_video_specs(store, script_id, merged_args)
    if not specs:
        return args, ["未找到可生成视频的镜头（请确认画面/提示词已就绪）"]

    project_id = resolve_project_id(store, ctx, script_id)
    emitter = ctx.work_context.get("emitter")
    ensure_generation_runner(store, emitter, ctx)

    jobs = await enqueue_and_wait_shot_video_specs(
        project_id=project_id,
        script_id=script_id,
        specs=specs,
        source="agent",
    )
    clips, errors = video_jobs_to_results(store, specs, jobs, shot_video=True)

    if not clips and errors:
        return args, errors

    merged = dict(args)
    existing = merged.get("clips")
    if isinstance(existing, list):
        merged["clips"] = [*existing, *clips]
    else:
        merged["clips"] = clips
    if not str(merged.get("observation", "")).strip():
        succeeded = len(clips)
        failed = len(errors)
        merged["observation"] = format_video_queue_observation(
            len(specs),
            succeeded,
            failed,
        )
    schedule_save(store)
    return merged, errors


async def generate_one_shot_video(
    store: MemoryStore,
    ctx: AgentRunContext,
    spec: ShotVideoGenSpec,
) -> None:
    """供生成队列串行调用的单条镜头视频生成入口。"""
    from core.interaction_log.media_log import media_log_scope

    semaphore = asyncio.Semaphore(1)
    with media_log_scope(
        project_id=str(ctx.project_id or ctx.work_context.get("project_id") or ""),
        script_id=str(ctx.script_id or ""),
        agent_name=str(ctx.agent_name or ""),
        step_id=str(ctx.step_id or ""),
        asset_id=str(spec.shot_id or spec.video_clip_asset_id or ""),
    ):
        _clip, err = await _generate_one_shot(store, ctx, spec, semaphore=semaphore)
    if err:
        raise RuntimeError(err)
