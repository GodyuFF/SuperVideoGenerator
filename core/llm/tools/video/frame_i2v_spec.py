"""画面图生视频模式：以 frame 为唯一图生源解析 video_clip 生成规格。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.assets.video_prompt import compose_video_clip_prompt
from core.edit.sub_shot_helpers import find_sub_shot_index_by_video_clip
from core.llm.tools.video.shot_spec import (
    ShotVideoGenSpec,
    VideoGenMode,
    _collect_sub_shot_image_urls,
)
from core.models.entities import TextAssetType
from core.models.video_text_asset import normalize_video_clip_content
from core.store.memory import MemoryStore

if TYPE_CHECKING:
    from core.models.entities import Shot


def locate_shot_for_video_clip(
    store: MemoryStore,
    script_id: str,
    video_clip_asset_id: str,
) -> tuple[Shot | None, int | None]:
    """在 VideoPlan 中定位 video_clip 所属的镜与子镜索引。"""
    plan = store.get_video_plan_for_script(script_id)
    if not plan:
        return None, None
    clip_id = video_clip_asset_id.strip()
    for shot in plan.shots:
        idx = find_sub_shot_index_by_video_clip(shot, clip_id)
        if idx is not None:
            return shot, idx
    return None, None


def _collect_frame_asset_ids(shot: Shot, sub_idx: int) -> list[str]:
    """收集子镜关联的 frame 文字资产 id（按 images 顺序）。"""
    if sub_idx < 0 or sub_idx >= len(shot.sub_shots):
        return []
    sub = shot.sub_shots[sub_idx]
    ids: list[str] = []
    seen: set[str] = set()
    for vid in sub.videos:
        fid = str(getattr(vid, "source_frame_asset_id", "") or "").strip()
        if fid and fid not in seen:
            ids.append(fid)
            seen.add(fid)
    for img in sub.images:
        fid = str(img.frame_asset_id or "").strip()
        if fid and fid not in seen:
            ids.append(fid)
            seen.add(fid)
    return ids


def resolve_frame_i2v_clip_spec(
    store: MemoryStore,
    script_id: str,
    video_clip_asset_id: str,
    *,
    shot_id: str = "",
    order: int = 0,
    sub_shot_idx: int | None = None,
    duration_sec: float | None = None,
    forced_video_mode: str | None = None,
    allowed_modes: list[str] | None = None,
) -> ShotVideoGenSpec:
    """从 VideoPlan 定位子镜，以 frame 为唯一图生源，video_clip 仅提供 motion prompt。"""
    asset = store.get_text_asset(video_clip_asset_id.strip())
    if not asset or asset.type != TextAssetType.VIDEO_CLIP:
        raise ValueError(f"video_clip 资产 {video_clip_asset_id} 不存在")

    shot, sub_idx = locate_shot_for_video_clip(store, script_id, video_clip_asset_id)
    if shot is None or sub_idx is None:
        raise ValueError(f"video_clip {video_clip_asset_id} 未绑定到 VideoPlan 子镜")
    if sub_shot_idx is not None:
        sub_idx = sub_shot_idx

    content = normalize_video_clip_content(asset.content)
    prompt = compose_video_clip_prompt(content, store=store)
    sub = shot.sub_shots[sub_idx]
    if (sub.description or "").strip():
        prompt = f"{prompt}。{sub.description.strip()}"

    if duration_sec is None:
        duration_ms = max(int(sub.end_ms or 0) - int(sub.start_ms or 0), 0)
        if duration_ms <= 0:
            duration_ms = max(int(shot.duration_ms or 0), 3000)
        raw_dur = content.get("duration_sec")
        try:
            dur = float(raw_dur) if raw_dur is not None else duration_ms / 1000.0
        except (TypeError, ValueError):
            dur = duration_ms / 1000.0
    else:
        dur = duration_sec
    dur = min(max(float(dur), 1.0), 18.0)

    frame_urls = _collect_sub_shot_image_urls(store, shot, sub_idx)
    frame_ids = _collect_frame_asset_ids(shot, sub_idx)
    forced = (forced_video_mode or "").strip().lower() or None

    mode: VideoGenMode
    image_url: str | None = None
    keyframe_urls: list[str] = []

    if forced == "text2video":
        mode = "text2video"
    elif len(frame_urls) >= 2 and (forced == "keyframes" or forced is None):
        mode = "keyframes"
        keyframe_urls = list(frame_urls)
        prompt = prompt + "。在关键帧之间生成流畅电影感过渡，保持主体与风格一致。"
    elif len(frame_urls) >= 1:
        if forced == "keyframes" and len(frame_urls) < 2:
            raise ValueError("关键帧模式需要至少 2 张已落盘画面，请先生成画面图片")
        mode = "img2video" if forced != "text2video" else "text2video"
        if mode == "img2video":
            image_url = frame_urls[0]
            prompt = prompt + "。以输入图片为基准添加自然动态与运镜。"
    elif forced in ("img2video", "keyframes"):
        raise ValueError("子镜 frame 尚无可用图片，无法使用图生/关键帧模式")
    else:
        mode = "text2video"

    source_frame = frame_ids[0] if frame_ids else ""

    if allowed_modes is not None:
        if not allowed_modes:
            raise ValueError("当前视频风格未配置 AI 生视频能力（video）")
        if mode not in allowed_modes:
            raise ValueError(
                f"当前视频风格不支持 {mode}，允许：{', '.join(allowed_modes)}"
            )

    sid = shot_id or str(content.get("shot_id") or "").strip() or shot.id
    ord_val = order if order else shot.order

    from core.llm.tools.video.shot_spec import validate_video_gen_mode_for_provider

    validate_video_gen_mode_for_provider(mode)
    return ShotVideoGenSpec(
        shot_id=sid,
        order=ord_val,
        mode=mode,
        prompt=prompt,
        image_url=image_url,
        keyframe_urls=keyframe_urls,
        duration_sec=dur,
        sub_shot_idx=sub_idx,
        source_frame_asset_id=source_frame,
        source_frame_asset_ids=list(frame_ids),
        video_clip_asset_id=asset.id,
    )
