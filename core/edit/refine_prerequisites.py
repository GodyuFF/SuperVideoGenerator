"""分镜复核前置媒体齐套检查（纯函数，不抛 ReturnToMaster）。"""

from __future__ import annotations

from typing import Any, Literal

from core.edit.sub_shot_helpers import first_sub_shot_image
from core.edit.sub_shot_produce import coerce_produce_mode, infer_produce_mode
from core.llm.tools.shared.media_list import is_placeholder_media_url, resolve_media_access
from core.models.entities import Shot, VideoStyleMode
from core.store.memory import MemoryStore

MissingKind = Literal["frame", "tts", "video"]
MissingStatus = Literal["missing", "generating", "inaccessible"]

_KIND_TO_AGENT: dict[MissingKind, str] = {
    "frame": "image_agent",
    "tts": "tts_agent",
    "video": "video_agent",
}

_RESUME_HINT = "上游生成完成后重新委派 storyboard_refine_agent"


def _media_accessible(store: MemoryStore, media_id: str | None) -> tuple[bool, MissingStatus | None]:
    """判断 media_id 是否可访问；不可用时返回状态。"""
    mid = str(media_id or "").strip()
    if not mid:
        return False, "missing"
    media = store.media_assets.get(mid)
    if media is None:
        return False, "missing"
    url = str(media.url or "").strip()
    if not url or is_placeholder_media_url(url):
        return False, "inaccessible"
    access = resolve_media_access(url)
    if access.get("is_accessible"):
        return True, None
    return False, "inaccessible"


def _generating_asset_ids(script_id: str) -> set[str]:
    """返回剧本生成队列中 queued/running 的 asset_id 集合。"""
    from core.generation.queue import get_generation_queue

    snap = get_generation_queue().snapshot_for_script(script_id)
    ids: set[str] = set()
    active = snap.get("active")
    if isinstance(active, dict):
        aid = str(active.get("asset_id") or "").strip()
        if aid:
            ids.add(aid)
    for job in snap.get("queued") or []:
        if not isinstance(job, dict):
            continue
        aid = str(job.get("asset_id") or "").strip()
        if aid:
            ids.add(aid)
    return ids


def _item(
    *,
    kind: MissingKind,
    shot_id: str,
    status: MissingStatus,
    detail: str,
    sub_shot_id: str = "",
    asset_id: str = "",
) -> dict[str, Any]:
    """构造 missing_items 元素。"""
    row: dict[str, Any] = {
        "kind": kind,
        "shot_id": shot_id,
        "status": status,
        "detail": detail,
    }
    if sub_shot_id:
        row["sub_shot_id"] = sub_shot_id
    if asset_id:
        row["asset_id"] = asset_id
    return row


def _check_frame(
    store: MemoryStore,
    shot: Shot,
    generating: set[str],
) -> list[dict[str, Any]]:
    """检查子镜 frame 配图是否就绪。"""
    gaps: list[dict[str, Any]] = []
    if not shot.sub_shots:
        gaps.append(
            _item(
                kind="frame",
                shot_id=shot.id,
                status="missing",
                detail="镜头无子镜，无法关联 frame",
            )
        )
        return gaps
    for sub in shot.sub_shots:
        img = first_sub_shot_image(sub)
        frame_id = str((img.frame_asset_id if img else "") or "").strip()
        media_id = str((img.media_id if img else "") or "").strip()
        if frame_id and frame_id in generating:
            gaps.append(
                _item(
                    kind="frame",
                    shot_id=shot.id,
                    sub_shot_id=sub.id,
                    asset_id=frame_id,
                    status="generating",
                    detail="frame 仍在生成队列中",
                )
            )
            continue
        if not frame_id and not media_id:
            gaps.append(
                _item(
                    kind="frame",
                    shot_id=shot.id,
                    sub_shot_id=sub.id,
                    status="missing",
                    detail="子镜未关联 frame / media",
                )
            )
            continue
        if frame_id and not media_id:
            frame_asset = store.text_assets.get(frame_id)
            media_id = str(
                (frame_asset.primary_media_id if frame_asset else "") or ""
            ).strip()
            if not media_id:
                gaps.append(
                    _item(
                        kind="frame",
                        shot_id=shot.id,
                        sub_shot_id=sub.id,
                        asset_id=frame_id,
                        status="missing",
                        detail="frame 资产尚无 primary_media_id",
                    )
                )
                continue
        ok, status = _media_accessible(store, media_id)
        if not ok:
            gaps.append(
                _item(
                    kind="frame",
                    shot_id=shot.id,
                    sub_shot_id=sub.id,
                    asset_id=frame_id or media_id,
                    status=status or "missing",
                    detail="frame 配图 media 不可访问",
                )
            )
    return gaps


def _check_tts(
    store: MemoryStore,
    shot: Shot,
    generating: set[str],
) -> list[dict[str, Any]]:
    """检查镜内 voice 轨是否已绑定可访问音频。"""
    gaps: list[dict[str, Any]] = []
    voice_clips = [
        clip
        for track in shot.audio_tracks
        if track.kind == "voice"
        for clip in track.clips
    ]
    if not voice_clips:
        gaps.append(
            _item(
                kind="tts",
                shot_id=shot.id,
                status="missing",
                detail="镜头无 voice 音频轨",
            )
        )
        return gaps
    for clip in voice_clips:
        mid = str(clip.media_id or "").strip()
        if not mid:
            gaps.append(
                _item(
                    kind="tts",
                    shot_id=shot.id,
                    status="missing",
                    detail="voice clip 未绑定 media_id",
                )
            )
            continue
        if mid in generating:
            gaps.append(
                _item(
                    kind="tts",
                    shot_id=shot.id,
                    asset_id=mid,
                    status="generating",
                    detail="配音仍在生成队列中",
                )
            )
            continue
        ok, status = _media_accessible(store, mid)
        if not ok:
            gaps.append(
                _item(
                    kind="tts",
                    shot_id=shot.id,
                    asset_id=mid,
                    status=status or "missing",
                    detail="配音 media 不可访问",
                )
            )
    return gaps


def _sub_needs_video(sub) -> bool:
    """ai_video 下是否要求该子镜已有视频成片。"""
    raw = getattr(sub, "produce_mode", None)
    mode = coerce_produce_mode(raw) if raw else infer_produce_mode(sub)
    return mode in ("text2video", "img2video")


def _check_video(
    store: MemoryStore,
    shot: Shot,
    generating: set[str],
    *,
    require_all_subs: bool = False,
) -> list[dict[str, Any]]:
    """检查需视频子镜的 video_clip / media 是否就绪。"""
    from core.llm.tools.video.source_urls import video_clip_asset_preview_url

    gaps: list[dict[str, Any]] = []
    if not shot.sub_shots:
        gaps.append(
            _item(
                kind="video",
                shot_id=shot.id,
                status="missing",
                detail="镜头无子镜，无法关联 video_clip",
            )
        )
        return gaps
    for sub in shot.sub_shots:
        if not require_all_subs and not _sub_needs_video(sub):
            continue
        if not sub.videos:
            gaps.append(
                _item(
                    kind="video",
                    shot_id=shot.id,
                    sub_shot_id=sub.id,
                    status="missing",
                    detail="子镜需视频但未关联 video_clip",
                )
            )
            continue
        for vid in sub.videos:
            clip_id = str(vid.video_clip_asset_id or "").strip()
            mid = str(vid.media_id or "").strip()
            if clip_id and clip_id in generating:
                gaps.append(
                    _item(
                        kind="video",
                        shot_id=shot.id,
                        sub_shot_id=sub.id,
                        asset_id=clip_id,
                        status="generating",
                        detail="video_clip 仍在生成队列中",
                    )
                )
                continue
            if mid:
                ok, status = _media_accessible(store, mid)
                if ok:
                    continue
                gaps.append(
                    _item(
                        kind="video",
                        shot_id=shot.id,
                        sub_shot_id=sub.id,
                        asset_id=clip_id or mid,
                        status=status or "missing",
                        detail="视频 media 不可访问",
                    )
                )
                continue
            if clip_id and video_clip_asset_preview_url(store, clip_id):
                continue
            gaps.append(
                _item(
                    kind="video",
                    shot_id=shot.id,
                    sub_shot_id=sub.id,
                    asset_id=clip_id,
                    status="missing" if not clip_id else "inaccessible",
                    detail="video_clip 尚无可用视频 media",
                )
            )
    return gaps


def suggested_agent_ids_for_gaps(missing_items: list[dict[str, Any]]) -> list[str]:
    """按缺口 kind 去重映射 suggested_agent_ids（稳定顺序）。"""
    order = ("image_agent", "tts_agent", "video_agent")
    found: set[str] = set()
    for item in missing_items:
        kind = str(item.get("kind") or "")
        agent = _KIND_TO_AGENT.get(kind)  # type: ignore[arg-type]
        if agent:
            found.add(agent)
    return [a for a in order if a in found]


def format_prerequisites_observation(missing_items: list[dict[str, Any]]) -> str:
    """生成回主编排的中文缺口摘要。"""
    counts: dict[str, int] = {"frame": 0, "tts": 0, "video": 0, "generating": 0}
    for item in missing_items:
        kind = str(item.get("kind") or "")
        if kind in counts:
            counts[kind] += 1
        if item.get("status") == "generating":
            counts["generating"] += 1
    parts: list[str] = []
    if counts["frame"]:
        parts.append(f"缺 frame {counts['frame']}")
    if counts["tts"]:
        parts.append(f"缺 TTS {counts['tts']}")
    if counts["video"]:
        parts.append(f"缺 video {counts['video']}")
    if counts["generating"]:
        parts.append(f"队列中 {counts['generating']}")
    summary = "、".join(parts) if parts else "上游媒体未齐套"
    return f"分镜复核前置检查未通过：{summary}。请先补齐后再委派 storyboard_refine_agent。"


def evaluate_refine_prerequisites(
    store: MemoryStore,
    script_id: str,
    *,
    style_mode: str | VideoStyleMode | None = None,
) -> dict[str, Any]:
    """评估复核前置是否齐套；返回 ready / checks / missing_items / suggested_agent_ids。"""
    script = store.get_script(script_id)
    if script is None:
        raise ValueError(f"剧本 {script_id} 不存在")
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        raise ValueError("未找到视频计划稿")

    mode_raw = style_mode
    if mode_raw is None:
        mode_raw = getattr(script, "style_mode", None) or plan.mode
    if isinstance(mode_raw, VideoStyleMode):
        mode = mode_raw.value
    else:
        mode = str(mode_raw or VideoStyleMode.STORYBOOK.value).strip() or "storybook"
    require_video = mode == VideoStyleMode.AI_VIDEO.value

    generating = _generating_asset_ids(script_id)
    missing: list[dict[str, Any]] = []
    for shot in sorted(plan.shots, key=lambda s: s.order):
        missing.extend(_check_frame(store, shot, generating))
        missing.extend(_check_tts(store, shot, generating))
        if require_video:
            missing.extend(
                _check_video(store, shot, generating, require_all_subs=True)
            )

    frame_ok = not any(m.get("kind") == "frame" for m in missing)
    tts_ok = not any(m.get("kind") == "tts" for m in missing)
    if require_video:
        video_check: str = (
            "ok" if not any(m.get("kind") == "video" for m in missing) else "fail"
        )
    else:
        video_check = "skipped"

    ready = frame_ok and tts_ok and video_check in ("ok", "skipped")
    suggested = suggested_agent_ids_for_gaps(missing) if not ready else []
    return {
        "ready": ready,
        "style_mode": mode,
        "shot_count": len(plan.shots),
        "plan_id": plan.id,
        "checks": {
            "frame": "ok" if frame_ok else "fail",
            "tts": "ok" if tts_ok else "fail",
            "video": video_check,
        },
        "missing_items": missing,
        "suggested_agent_ids": suggested,
        "resume_hint": _RESUME_HINT,
    }


def build_return_to_master_payload(
    evaluation: dict[str, Any],
    *,
    agent_name: str,
    step_id: str,
    script_id: str,
) -> tuple[str, dict[str, Any]]:
    """从评估结果组装 ReturnToMasterError 的 message 与 structured。"""
    missing = list(evaluation.get("missing_items") or [])
    observation = format_prerequisites_observation(missing)
    structured: dict[str, Any] = {
        "agent_name": agent_name,
        "step_id": step_id,
        "script_id": script_id,
        "missing_items": missing,
        "suggested_agent_ids": list(evaluation.get("suggested_agent_ids") or []),
        "resume_hint": str(evaluation.get("resume_hint") or _RESUME_HINT),
        "checks": dict(evaluation.get("checks") or {}),
        "style_mode": evaluation.get("style_mode"),
    }
    return observation, structured
