"""从 VideoPlan Shot 解析 Agnes 视频生成规格。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from core.assets.video_prompt import compose_video_clip_prompt
from core.llm.tools.video.agnes_client import KEYFRAMES_MODE_MARKER
from core.llm.tools.video.source_urls import (
    collect_video_clip_source_urls,
    collect_video_source_image_urls,
    frame_asset_preview_url,
    resolve_image_url_for_video,
)
from core.models.entities import Shot, TextAssetType
from core.models.video_text_asset import normalize_video_clip_content
from core.store.memory import MemoryStore

VideoGenMode = Literal["text2video", "img2video", "keyframes"]


def validate_video_gen_mode_for_provider(mode: VideoGenMode) -> None:
    """校验当前视频 Provider 是否支持目标生视频子模式。"""
    from core.llm.tools.shared.media_capability import assert_video_mode_supported
    from core.llm.tools.video.settings import get_video_gen_manager

    provider = get_video_gen_manager().get_settings().provider
    assert_video_mode_supported(provider, mode)


@dataclass
class ShotVideoGenSpec:
    """单镜视频生成参数。"""

    shot_id: str
    order: int
    mode: VideoGenMode
    prompt: str
    image_url: str | None
    keyframe_urls: list[str]
    duration_sec: float
    sub_shot_idx: int
    source_frame_asset_id: str = ""
    source_frame_asset_ids: list[str] = field(default_factory=list)
    video_clip_asset_id: str = ""


def resolve_video_clip_gen_spec(
    store: MemoryStore,
    video_clip_asset_id: str,
    *,
    shot_id: str = "",
    order: int = 0,
    sub_shot_idx: int = 0,
    duration_sec: float | None = None,
    forced_video_mode: str | None = None,
    allowed_modes: list[str] | None = None,
) -> ShotVideoGenSpec:
    """从 video_clip 文字资产解析视频生成规格。"""
    asset = store.get_text_asset(video_clip_asset_id.strip())
    if not asset or asset.type != TextAssetType.VIDEO_CLIP:
        raise ValueError(f"video_clip 资产 {video_clip_asset_id} 不存在")
    content = normalize_video_clip_content(asset.content)
    prompt = compose_video_clip_prompt(content, store=store)
    dur = duration_sec
    if dur is None:
        raw_dur = content.get("duration_sec")
        try:
            dur = float(raw_dur) if raw_dur is not None else 5.0
        except (TypeError, ValueError):
            dur = 5.0
    dur = min(max(float(dur), 1.0), 18.0)
    forced = forced_video_mode or (
        content.get("video_mode") if content.get("video_mode") != "auto" else None
    )
    explicit_urls = collect_video_clip_source_urls(store, content)
    sid = shot_id or str(content.get("shot_id") or "").strip() or asset.id
    if explicit_urls:
        mode, prompt, image_url, keyframe_urls = _apply_explicit_source_urls(
            explicit_urls=explicit_urls,
            allowed_modes=allowed_modes,
            forced_mode=forced,
            base_prompt=prompt,
        )
    else:
        mode = "text2video"
        image_url = None
        keyframe_urls = []
        if forced == "text2video" or (not forced and "text2video" in (allowed_modes or [])):
            mode = "text2video"
        elif forced in ("img2video", "keyframes"):
            raise ValueError("video_clip 缺少可用参考图，无法使用图生/关键帧模式")
    if allowed_modes is not None:
        if not allowed_modes:
            raise ValueError("当前视频风格未配置 AI 生视频能力（video）")
        if mode not in allowed_modes:
            raise ValueError(
                f"当前视频风格不支持 {mode}，允许：{', '.join(allowed_modes)}"
            )
    validate_video_gen_mode_for_provider(mode)
    return ShotVideoGenSpec(
        shot_id=sid,
        order=order,
        mode=mode,
        prompt=prompt,
        image_url=image_url,
        keyframe_urls=keyframe_urls,
        duration_sec=dur,
        sub_shot_idx=sub_shot_idx,
        video_clip_asset_id=asset.id,
    )


def _resolve_image_url(store: MemoryStore, media_id: str) -> str:
    """将 media_id 解析为 Agnes 可用的图片 URL。"""
    return resolve_image_url_for_video(store, media_id)


def _frame_asset_preview_url(store: MemoryStore, frame_asset_id: str) -> str:
    """从 frame 文字资产解析主图 media URL。"""
    return frame_asset_preview_url(store, frame_asset_id)


def _build_motion_prompt(shot: Shot, sub_idx: int) -> str:
    """组装视频 motion prompt。"""
    sub = shot.sub_shots[sub_idx]
    parts: list[str] = []
    if (shot.review_note or "").strip():
        parts.append(shot.review_note.strip())
    if (sub.description or "").strip():
        parts.append(sub.description.strip())
    if (sub.camera_motion or "").strip() and sub.camera_motion != "static":
        parts.append(f"camera: {sub.camera_motion}")
    text = "，".join(parts).strip()
    if text:
        return text
    return f"镜 {shot.order + 1} 动态画面，自然运镜，电影感光照"


def _collect_sub_shot_image_urls(store: MemoryStore, shot: Shot, sub_idx: int) -> list[str]:
    """收集子镜全部可访问画面 URL（按 images 顺序）。"""
    if sub_idx < 0 or sub_idx >= len(shot.sub_shots):
        return []
    sub = shot.sub_shots[sub_idx]
    urls: list[str] = []
    seen: set[str] = set()
    for img in sub.images:
        if img.media_id:
            try:
                url = _resolve_image_url(store, img.media_id)
                if url and url not in seen:
                    urls.append(url)
                    seen.add(url)
            except ValueError:
                pass
        frame_id = (img.frame_asset_id or "").strip()
        if frame_id:
            url = _frame_asset_preview_url(store, frame_id)
            if url and url not in seen:
                urls.append(url)
                seen.add(url)
    return urls


def _is_keyframes_marker(video_prompt: str) -> bool:
    return (video_prompt or "").strip() == KEYFRAMES_MODE_MARKER


def _apply_explicit_source_urls(
    *,
    explicit_urls: list[str],
    allowed_modes: list[str] | None,
    forced_mode: str | None,
    base_prompt: str,
) -> tuple[VideoGenMode, str, str | None, list[str]]:
    """根据用户显式选择的参考图 URL 决定文生/图生/关键帧模式。"""
    if not explicit_urls:
        raise ValueError("所选参考图均不可用，请确认画面/图片已生成并落盘")

    modes = allowed_modes or ["text2video", "img2video", "keyframes"]
    want = (forced_mode or "").strip().lower()
    if want == "keyframes" or (not want and len(explicit_urls) >= 2 and "keyframes" in modes):
        if len(explicit_urls) < 2:
            raise ValueError("关键帧模式需要至少 2 张参考图")
        if "keyframes" not in modes:
            raise ValueError("当前视频风格不支持 keyframes 关键帧模式")
        return (
            "keyframes",
            base_prompt + "。在关键帧之间生成流畅电影感过渡，保持主体与风格一致。",
            None,
            list(explicit_urls),
        )
    if want == "text2video":
        raise ValueError("已选择参考图时不能使用文生视频，请改用图生或关键帧模式")
    if "img2video" not in modes:
        raise ValueError("当前视频风格不支持 img2video 图生视频")
    return (
        "img2video",
        base_prompt + "。以输入图片为基准添加自然动态与运镜。",
        explicit_urls[0],
        [],
    )


def _normalize_element_refs(raw: dict[str, Any] | None) -> dict[str, list[str]]:
    """清洗 API 传入的 element_refs，仅保留 frame 桶。"""
    if not raw or not isinstance(raw, dict):
        return {}
    val = raw.get("frame")
    if val is None:
        return {}
    ids = val if isinstance(val, list) else [val]
    cleaned = [str(x).strip() for x in ids if str(x).strip()]
    if not cleaned:
        return {}
    return {"frame": cleaned}


def resolve_shot_video_gen_spec(
    store: MemoryStore,
    shot: Shot,
    *,
    script_id: str = "",
    sub_shot_idx: int = 0,
    preferred_frame_asset_id: str = "",
    source_frame_asset_ids: list[str] | None = None,
    source_element_refs: dict[str, Any] | None = None,
    forced_video_mode: str | None = None,
    allowed_modes: list[str] | None = None,
) -> ShotVideoGenSpec:
    """从镜内子镜、显式参考选择或画面推断文生/图生/关键帧模式。"""
    if not shot.sub_shots:
        raise ValueError(f"镜头 {shot.id} 缺少子镜，无法生成视频")

    idx = min(max(sub_shot_idx, 0), len(shot.sub_shots) - 1)
    sub = shot.sub_shots[idx]
    duration_ms = max(int(sub.end_ms or 0) - int(sub.start_ms or 0), 0)
    if duration_ms <= 0:
        duration_ms = max(int(shot.duration_ms or 0), 3000)
    duration_sec = min(max(duration_ms / 1000.0, 1.0), 18.0)

    prompt = _build_motion_prompt(shot, idx)
    image_urls = _collect_sub_shot_image_urls(store, shot, idx)

    explicit_frames = [str(x).strip() for x in (source_frame_asset_ids or []) if str(x).strip()]
    if not explicit_frames and (preferred_frame_asset_id or "").strip():
        explicit_frames = [preferred_frame_asset_id.strip()]
    explicit_refs = _normalize_element_refs(source_element_refs)
    has_explicit = bool(explicit_frames or explicit_refs)

    video_clip_id = ""
    for vid in sub.videos:
        vc_id = str(getattr(vid, "video_clip_asset_id", "") or "").strip()
        if vc_id:
            video_clip_id = vc_id
            break
    if not has_explicit and video_clip_id:
        if script_id:
            from core.guards.script_style import normalize_style_mode_id
            from core.llm.master.actions import uses_frame_i2v_pipeline

            script = store.get_script(script_id)
            style_id = normalize_style_mode_id(script.style_mode if script else None)
            if uses_frame_i2v_pipeline(style_id or ""):
                from core.llm.tools.video.frame_i2v_spec import resolve_frame_i2v_clip_spec

                return resolve_frame_i2v_clip_spec(
                    store,
                    script_id,
                    video_clip_id,
                    shot_id=shot.id,
                    order=shot.order,
                    sub_shot_idx=idx,
                    forced_video_mode=forced_video_mode,
                    allowed_modes=allowed_modes,
                )
        spec = resolve_video_clip_gen_spec(
            store,
            video_clip_id,
            shot_id=shot.id,
            order=shot.order,
            sub_shot_idx=idx,
            forced_video_mode=forced_video_mode,
            allowed_modes=allowed_modes,
        )
        return spec

    source_frame = explicit_frames[0] if explicit_frames else ""
    if not source_frame:
        for vid in sub.videos:
            fid = str(getattr(vid, "source_frame_asset_id", "") or "").strip()
            if fid:
                source_frame = fid
                break

    primary = sub.images[0] if sub.images else None
    video_prompt = (primary.video_prompt if primary else "") or ""

    mode: VideoGenMode
    image_url: str | None = None
    keyframe_urls: list[str] = []

    if has_explicit:
        explicit_urls = collect_video_source_image_urls(
            store,
            frame_asset_ids=explicit_frames,
            element_refs=explicit_refs,
        )
        mode, prompt, image_url, keyframe_urls = _apply_explicit_source_urls(
            explicit_urls=explicit_urls,
            allowed_modes=allowed_modes,
            forced_mode=forced_video_mode,
            base_prompt=prompt,
        )
    elif _is_keyframes_marker(video_prompt):
        mode = "keyframes"
        keyframe_urls = list(image_urls)
        if len(keyframe_urls) < 2:
            raise ValueError("关键帧模式需要至少 2 张已落盘画面，请先生成画面图片")
        prompt = (
            prompt
            + "。在关键帧之间生成流畅电影感过渡，保持主体与风格一致。"
        )
    elif source_frame:
        mode = "img2video"
        image_url = _frame_asset_preview_url(store, source_frame)
        if not image_url:
            raise ValueError(f"源画面 {source_frame} 尚无可用图片，请先生成画面")
        prompt = prompt + "。以输入图片为基准添加自然动态与运镜。"
    elif primary and primary.kind == "video" and (primary.media_id or image_urls):
        mode = "img2video"
        if primary.media_id:
            image_url = _resolve_image_url(store, primary.media_id)
        else:
            image_url = image_urls[0]
        prompt = prompt + "。以输入图片为基准添加自然动态与运镜。"
    elif image_urls:
        mode = "img2video"
        image_url = image_urls[0]
        prompt = prompt + "。以输入图片为基准添加自然动态与运镜。"
    else:
        mode = "text2video"
        if video_prompt and not _is_keyframes_marker(video_prompt):
            prompt = video_prompt.strip()

    if allowed_modes is not None:
        if not allowed_modes:
            raise ValueError("当前视频风格未配置 AI 生视频能力（video）")
        if mode not in allowed_modes:
            raise ValueError(
                f"当前视频风格不支持 {mode}，允许：{', '.join(allowed_modes)}"
            )

    validate_video_gen_mode_for_provider(mode)
    return ShotVideoGenSpec(
        shot_id=shot.id,
        order=shot.order,
        mode=mode,
        prompt=prompt,
        image_url=image_url,
        keyframe_urls=keyframe_urls,
        duration_sec=duration_sec,
        sub_shot_idx=idx,
        source_frame_asset_id=source_frame,
        source_frame_asset_ids=explicit_frames if has_explicit else ([source_frame] if source_frame else []),
    )
