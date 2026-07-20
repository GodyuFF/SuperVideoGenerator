"""按镜头 TTS 合成与落盘。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from core.execution.cancel import ExecutionCancelledError, check_cancelled, gather_with_cancel
from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.tts.extract import build_narration_payload
from core.llm.tools.tts.settings import TtsSettings, get_tts_manager
from core.models.entities import MediaAsset, MediaAssetType, new_id
from core.store.memory import MemoryStore
from core.store.project_paths import script_media_dir
from core.tts.duration import duration_ms_from_target
from core.tts.engine import build_runtime_config, is_tts_available, synthesize_speech
from core.tts.subtitle import subtitle_cues_from_submaker
from core.llm.hook.react_guard import TtsAbortError

logger = logging.getLogger("core.llm.tools.tts.synthesize")

TTS_MAX_ATTEMPTS = 3
# SubMaker cue 与 MP3 文件时长偏差超过此阈值时记录 duration_drift_ms
_SUBMAKER_FILE_DRIFT_MS = 150


def _resolve_synthesized_duration_ms(
    output_path: Path,
    sub_maker: Any,
) -> tuple[int, int]:
    """解析合成时长：优先本地文件探测，SubMaker 仅作兜底；返回 (duration_ms, drift_ms)。"""
    file_ms = duration_ms_from_target(output_path) if output_path.is_file() else 0
    submaker_ms = duration_ms_from_target(sub_maker) if sub_maker is not None else 0
    duration_ms = file_ms if file_ms > 0 else submaker_ms
    drift_ms = 0
    if file_ms > 0 and submaker_ms > 0:
        drift = abs(file_ms - submaker_ms)
        if drift > _SUBMAKER_FILE_DRIFT_MS:
            drift_ms = drift
    return duration_ms, drift_ms


def slim_synthesize_args(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    obs = str(args.get("observation", "")).strip()
    if obs:
        out["observation"] = obs
    shot_ids = args.get("shot_ids")
    if isinstance(shot_ids, list) and shot_ids:
        out["shot_ids"] = [str(s).strip() for s in shot_ids if str(s).strip()]
    for key in ("plan_status", "remaining_plan"):
        if key in args:
            out[key] = args[key]
    return out if out else dict(args)


def collect_narration_items(
    store: MemoryStore,
    script_id: str,
    args: dict[str, Any],
) -> list[dict[str, Any]]:
    payload = build_narration_payload(store, script_id)
    items = list(payload.get("items") or [])
    filter_ids = args.get("shot_ids")
    if isinstance(filter_ids, list) and filter_ids:
        allowed = {str(s).strip() for s in filter_ids if str(s).strip()}
        items = [item for item in items if str(item.get("shot_id")) in allowed]
    return items


async def _emit_tts_progress(ctx: AgentRunContext, **payload: Any) -> None:
    emitter = ctx.work_context.get("emitter")
    if emitter is None:
        return
    await emitter.emit(
        {
            "type": "tts_gen_progress",
            "script_id": ctx.script_id,
            "step_id": ctx.step_id,
            **payload,
        }
    )


def _synthesize_one_sync(
    item: dict[str, Any],
    *,
    store: MemoryStore,
    project_id: str,
    script_id: str,
    settings: TtsSettings,
    resolved_api_key: str | None,
) -> dict[str, Any] | None:
    check_cancelled(script_id)
    runtime = build_runtime_config(settings, resolved_api_key)
    if not is_tts_available(runtime):
        raise TtsAbortError("synthesize", "TTS 未启用或缺少必要配置。")

    shot_id = str(item["shot_id"])
    text = str(item["text"])
    media_id = str(item.get("asset_id") or new_id("media"))
    label = str(item.get("label") or f"shot_{item.get('order', 0)}_narration")

    media_dir = script_media_dir(project_id, script_id)
    media_dir.mkdir(parents=True, exist_ok=True)
    output_path = media_dir / f"{media_id}.mp3"

    last_error = "未知错误"
    sub_maker = None
    duration_ms = 0
    subtitle_cues: list[dict[str, Any]] = []
    duration_drift_ms = 0
    used_planned = False

    plan = store.get_video_plan_for_script(script_id)
    shot = None
    if plan:
        shot = next((s for s in plan.shots if s.id == shot_id), None)

    _shot_voice_clips = (
        [c for t in shot.audio_tracks if t.kind == "voice" for c in t.clips if c.text.strip()]
        if shot
        else []
    )
    if shot and _shot_voice_clips:
        from core.tts.planned_synthesis import synthesize_shot_with_plan

        try:
            result = synthesize_shot_with_plan(shot, output_path, runtime, store=store)
            duration_ms = result.duration_ms
            subtitle_cues = result.subtitle_cues
            duration_drift_ms = result.duration_drift_ms
            used_planned = result.used_planned_timeline
            if duration_ms > 0 and output_path.is_file():
                sub_maker = True  # sentinel
        except Exception as e:
            last_error = str(e)
            logger.warning("planned tts failed shot=%s: %s", shot_id, e)

    if sub_maker is None:
        for attempt in range(1, TTS_MAX_ATTEMPTS + 1):
            try:
                sub_maker = synthesize_speech(text, str(output_path), runtime)
                if sub_maker is not None and output_path.is_file() and output_path.stat().st_size > 0:
                    break
                last_error = f"第 {attempt} 次合成未产出有效音频"
            except Exception as e:
                last_error = str(e)
                logger.warning("tts synthesize attempt %s failed shot=%s: %s", attempt, shot_id, e)
            if output_path.is_file() and output_path.stat().st_size == 0:
                output_path.unlink(missing_ok=True)

        if sub_maker is None or not output_path.is_file():
            raise TtsAbortError(
                "synthesize",
                f"镜头 {shot_id} 配音合成失败（已重试 {TTS_MAX_ATTEMPTS} 次）：{last_error}",
            )

        duration_ms, submaker_drift = _resolve_synthesized_duration_ms(output_path, sub_maker)
        if submaker_drift > duration_drift_ms:
            duration_drift_ms = submaker_drift
        subtitle_cues = subtitle_cues_from_submaker(sub_maker)

    return {
        "shot_id": shot_id,
        "asset_id": media_id,
        "label": label,
        "url": str(output_path.resolve()),
        "duration_ms": duration_ms,
        "voice_name": runtime.voice_name,
        "provider": settings.provider,
        "text": text,
        "order": item.get("order", 0),
        "subtitle_cues": subtitle_cues,
        "duration_drift_ms": duration_drift_ms,
        "used_planned_timeline": used_planned,
    }


async def _synthesize_one(
    item: dict[str, Any],
    *,
    store: MemoryStore,
    project_id: str,
    script_id: str,
    settings: TtsSettings,
    resolved_api_key: str | None,
    semaphore: asyncio.Semaphore,
    ctx: AgentRunContext,
    index: int,
    total: int,
) -> dict[str, Any] | None:
    async with semaphore:
        await _emit_tts_progress(
            ctx,
            total=total,
            index=index,
            shot_id=item.get("shot_id"),
            status="started",
        )
        result = await asyncio.to_thread(
            _synthesize_one_sync,
            item,
            store=store,
            project_id=project_id,
            script_id=script_id,
            settings=settings,
            resolved_api_key=resolved_api_key,
        )
        await _emit_tts_progress(
            ctx,
            total=total,
            index=index,
            shot_id=item.get("shot_id"),
            status="completed" if result else "failed",
            asset_id=(result or {}).get("asset_id"),
        )
        return result


async def run_concurrent_tts_synthesis(
    store: MemoryStore,
    script_id: str,
    args: dict[str, Any],
    ctx: AgentRunContext,
) -> tuple[list[dict[str, Any]], str]:
    project_id = str(ctx.work_context.get("project_id", ""))
    items = collect_narration_items(store, script_id, args)
    if not items:
        return [], "未找到可合成的旁白文案，请先完成分镜并在 audio_tracks voice clip 填写 text。"

    check_cancelled(ctx.script_id)
    manager = get_tts_manager()
    settings = manager.get_settings()
    resolved_key = manager.resolved_api_key()
    concurrency = max(1, int(settings.max_concurrency or 3))
    semaphore = asyncio.Semaphore(concurrency)

    tasks = [
        _synthesize_one(
            item,
            store=store,
            project_id=project_id,
            script_id=script_id,
            settings=settings,
            resolved_api_key=resolved_key,
            semaphore=semaphore,
            ctx=ctx,
            index=i + 1,
            total=len(items),
        )
        for i, item in enumerate(items)
    ]
    results = await gather_with_cancel(ctx.script_id, tasks)
    synthesized = [r for r in results if r]
    if not synthesized:
        raise TtsAbortError("synthesize", "所有镜头配音合成均失败。")
    if len(synthesized) < len(items):
        raise TtsAbortError(
            "synthesize",
            f"部分镜头配音失败：成功 {len(synthesized)}/{len(items)}。",
        )

    observation = str(args.get("observation", "")).strip()
    if not observation:
        observation = f"已为 {len(synthesized)} 个镜头合成配音。"
    enriched = dict(args)
    enriched["tracks"] = synthesized
    enriched["observation"] = observation
    enriched["line_count"] = len(synthesized)
    return synthesized, observation


def persist_single_synthesized_audio(
    store: MemoryStore,
    ctx: AgentRunContext,
    item: dict[str, Any],
) -> MediaAsset | None:
    from core.llm.agent.llm_action import _persist_media
    from core.models.entities import MediaAsset, MediaAssetType, StepOutput, new_id

    url = str(item.get("url", "")).strip()
    if not url or not Path(url).is_file():
        return None

    script_id = str(ctx.work_context.get("script_id") or ctx.script_id)
    project_id = str(ctx.work_context.get("project_id", ""))
    shot_id = str(item.get("shot_id", "")).strip()
    media_id = str(item.get("asset_id") or new_id("media"))
    label = str(item.get("label") or "narration")
    file_ms = duration_ms_from_target(url)
    duration_ms = file_ms if file_ms > 0 else int(item.get("duration_ms") or 0)
    used_planned = bool(item.get("used_planned_timeline"))
    meta = {
        "shot_id": shot_id,
        "duration_ms": duration_ms,
        "voice_name": str(item.get("voice_name") or ""),
        "provider": str(item.get("provider") or ""),
        "narration_text": str(item.get("text") or "")[:500],
    }
    drift_ms = int(item.get("duration_drift_ms") or 0)
    if drift_ms > _SUBMAKER_FILE_DRIFT_MS:
        meta["duration_drift_ms"] = drift_ms
    if used_planned:
        meta["used_planned_timeline"] = True
    subtitle_cues = item.get("subtitle_cues")
    if isinstance(subtitle_cues, list) and subtitle_cues:
        meta["subtitle_cues"] = subtitle_cues
    if shot_id:
        from core.assets.regenerate import mark_media_superseded

        for existing in store.list_media_for_script(script_id, MediaAssetType.AUDIO):
            if existing.id == media_id:
                continue
            existing_shot = str((existing.metadata or {}).get("shot_id") or "").strip()
            if existing_shot != shot_id:
                continue
            if (existing.metadata or {}).get("superseded"):
                continue
            mark_media_superseded(store, existing.id)

    media = _persist_media(
        store,
        project_id=project_id,
        script_id=script_id,
        media_type=MediaAssetType.AUDIO,
        name=label,
        url=url,
        asset_id=media_id,
        metadata=meta,
    )
    ctx.outputs.append(
        StepOutput(
            kind="audio",
            label=label,
            asset_id=media.id,
            url=media.url,
        )
    )
    return media
