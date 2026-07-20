"""Agent 批处理与生成队列之间的桥接：拆条入队并等待完成。"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from core.generation.models import GenerationJob, GenerationSource
from core.generation.queue import get_generation_queue
from core.generation.runner import run_generation_job
from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.image.errors import ImageGenFailureItem, build_failure_item
from core.llm.tools.video.shot_spec import ShotVideoGenSpec
from core.models.entities import MediaAssetType
from core.store.memory import MemoryStore


def resolve_project_id(
    store: MemoryStore,
    ctx: AgentRunContext,
    script_id: str,
) -> str:
    """从上下文或剧本记录解析 project_id。"""
    project_id = str(ctx.project_id or ctx.work_context.get("project_id") or "").strip()
    if project_id:
        return project_id
    script = store.get_script(script_id)
    return script.project_id if script else ""


def ensure_generation_runner(
    store: MemoryStore,
    emitter: Any | None,
    agent_ctx: AgentRunContext | None = None,
) -> None:
    """确保全局队列已绑定当前 store 对应的单条执行器。"""
    q = get_generation_queue()

    async def _runner(job: GenerationJob) -> None:
        await run_generation_job(store, emitter, job, parent_ctx=agent_ctx)

    q.set_runner(_runner)


async def enqueue_and_wait_image_items(
    *,
    project_id: str,
    script_id: str,
    items: list[dict[str, Any]],
    source: GenerationSource = "agent",
) -> list[GenerationJob]:
    """将生图 items 逐条入队并等待全部结束。"""
    q = get_generation_queue()
    ids: list[str] = []
    for item in items:
        asset_id = str(item.get("source_text_asset_id") or item.get("asset_id") or "")
        label = str(item.get("name") or asset_id)
        variant_id = item.get("variant_id")
        job = await q.enqueue(
            project_id=project_id,
            script_id=script_id,
            kind="image",
            asset_id=asset_id,
            label=label,
            source=source,
            variant_id=str(variant_id) if variant_id else None,
            payload=item,
        )
        ids.append(job.id)
    return await q.wait_until_done(ids)


async def _enqueue_and_wait_video_specs(
    *,
    project_id: str,
    script_id: str,
    specs: list[ShotVideoGenSpec],
    source: GenerationSource = "agent",
    shot_video: bool = False,
) -> list[GenerationJob]:
    """将视频规格逐条入队并等待全部结束（clip / shot 共用）。"""
    q = get_generation_queue()
    ids: list[str] = []
    for spec in specs:
        asset_id = str(spec.video_clip_asset_id or spec.shot_id or "")
        if shot_video:
            label = f"镜头{spec.order + 1}"
        else:
            label = f"video_clip_{asset_id[-8:]}" if asset_id else "video_clip"
        payload = dict(asdict(spec))
        if shot_video:
            payload["shot_video"] = True
        job = await q.enqueue(
            project_id=project_id,
            script_id=script_id,
            kind="video",
            asset_id=asset_id,
            label=label,
            source=source,
            payload=payload,
        )
        ids.append(job.id)
    return await q.wait_until_done(ids)


async def enqueue_and_wait_video_clip_specs(
    *,
    project_id: str,
    script_id: str,
    specs: list[ShotVideoGenSpec],
    source: GenerationSource = "agent",
) -> list[GenerationJob]:
    """将 video_clip 规格逐条入队并等待全部结束。"""
    return await _enqueue_and_wait_video_specs(
        project_id=project_id,
        script_id=script_id,
        specs=specs,
        source=source,
        shot_video=False,
    )


async def enqueue_and_wait_shot_video_specs(
    *,
    project_id: str,
    script_id: str,
    specs: list[ShotVideoGenSpec],
    source: GenerationSource = "agent",
) -> list[GenerationJob]:
    """将镜头视频规格逐条入队并等待全部结束。"""
    return await _enqueue_and_wait_video_specs(
        project_id=project_id,
        script_id=script_id,
        specs=specs,
        source=source,
        shot_video=True,
    )


def rebuild_generated_image_item(
    store: MemoryStore,
    item: dict[str, Any],
) -> dict[str, Any] | None:
    """从 store 回填单条生图成功结果。"""
    source_id = str(item.get("source_text_asset_id") or item.get("asset_id") or "")
    if not source_id:
        return None
    text_asset = store.get_text_asset(source_id)
    if not text_asset or not text_asset.primary_media_id:
        return None
    media = store.media_assets.get(text_asset.primary_media_id)
    if not media:
        return None
    return {**item, "url": media.url, "media_id": media.id}


def image_jobs_to_results(
    store: MemoryStore,
    items: list[dict[str, Any]],
    jobs: list[GenerationJob],
) -> tuple[list[dict[str, Any]], list[ImageGenFailureItem]]:
    """根据队列任务结果组装生图成功项与失败项。"""
    item_by_asset = {
        str(i.get("source_text_asset_id") or i.get("asset_id") or ""): i for i in items
    }
    generated: list[dict[str, Any]] = []
    failures: list[ImageGenFailureItem] = []
    for job in jobs:
        item = item_by_asset.get(job.asset_id) or (job.payload or {})
        if job.status == "done":
            enriched = rebuild_generated_image_item(store, item)
            if enriched:
                generated.append(enriched)
            continue
        if job.status == "failed":
            failures.append(
                build_failure_item(
                    source_text_asset_id=str(
                        item.get("source_text_asset_id") or job.asset_id
                    ),
                    asset_name=str(item.get("name") or job.label or job.asset_id),
                    image_prompt=str(item.get("image_prompt") or ""),
                    error_message=str(job.error or "生图失败"),
                )
            )
    return generated, failures


def rebuild_video_clip_from_spec(
    store: MemoryStore,
    spec: ShotVideoGenSpec,
) -> dict[str, Any] | None:
    """从 store 回填 video_clip 生成结果。"""
    clip_id = str(spec.video_clip_asset_id or "").strip()
    if not clip_id:
        return None
    asset = store.get_text_asset(clip_id)
    if not asset or not asset.primary_media_id:
        return None
    media = store.media_assets.get(asset.primary_media_id)
    if not media:
        return None
    return {
        "video_clip_asset_id": clip_id,
        "shot_id": spec.shot_id,
        "url": media.url,
        "asset_id": media.id,
        "label": media.name,
        "mode": spec.mode,
        "duration_ms": int(spec.duration_sec * 1000),
    }


def rebuild_shot_clip_from_spec(
    store: MemoryStore,
    spec: ShotVideoGenSpec,
) -> dict[str, Any] | None:
    """从 store 回填镜头视频生成结果。"""
    shot_id = str(spec.shot_id or "").strip()
    if not shot_id:
        return None
    candidates = [
        media
        for media in store.media_assets.values()
        if media.type == MediaAssetType.VIDEO
        and str(media.metadata.get("shot_id") or "") == shot_id
    ]
    if not candidates:
        return None
    media = max(candidates, key=lambda m: m.created_at or "")
    return {
        "shot_id": shot_id,
        "url": media.url,
        "asset_id": media.id,
        "label": media.name,
        "mode": spec.mode,
        "duration_ms": int(spec.duration_sec * 1000),
    }


def video_jobs_to_results(
    store: MemoryStore,
    specs: list[ShotVideoGenSpec],
    jobs: list[GenerationJob],
    *,
    shot_video: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    """根据队列任务结果组装视频 clip 条目与错误信息。"""
    spec_by_asset = {
        str(s.video_clip_asset_id or s.shot_id or ""): s for s in specs
    }
    clips: list[dict[str, Any]] = []
    errors: list[str] = []
    for job in jobs:
        spec = spec_by_asset.get(job.asset_id)
        if job.status == "done":
            if spec is None:
                continue
            clip = (
                rebuild_shot_clip_from_spec(store, spec)
                if shot_video
                else rebuild_video_clip_from_spec(store, spec)
            )
            if clip:
                clips.append(clip)
            continue
        if job.status == "failed" and spec is not None:
            prefix = f"镜头 {spec.shot_id}" if shot_video else f"video_clip {spec.video_clip_asset_id}"
            errors.append(f"{prefix}：{job.error or '视频生成失败'}")
    return clips, errors


def format_video_queue_observation(
    total: int,
    succeeded: int,
    failed: int,
) -> str:
    """格式化视频批处理 observation 摘要。"""
    return f"已入队并完成 {total} 条视频生成（成功 {succeeded}，失败 {failed}）"
