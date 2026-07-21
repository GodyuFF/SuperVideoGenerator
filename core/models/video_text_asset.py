"""视频文字资产（video_clip）领域模型：生视频描述、简述、标签与参考图关联。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

VIDEO_TEXT_ASSET_TYPES = frozenset({"video_clip"})

VideoClipMode = Literal["auto", "text2video", "img2video", "keyframes"]


class VideoClipContent(BaseModel):
    """video_clip 文字资产 content 结构。"""

    summary: str = ""
    video_prompt: str = ""
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    video_mode: VideoClipMode = "auto"
    duration_sec: float | None = None
    camera_motion: str = ""
    element_refs: dict[str, list[str]] = Field(default_factory=dict)
    """关联资产 → 子形象（variant id）；缺省时用主形象/primary。"""
    variant_refs: dict[str, str] = Field(default_factory=dict)
    media_refs: list[str] = Field(default_factory=list)
    reference_order: list[str] = Field(default_factory=lambda: ["frame"])
    shot_id: str = ""
    sub_shot_id: str = ""
    prompt_locked: bool = False
    prompt_version: int = 0


def is_video_text_asset(type_val: str) -> bool:
    """判断是否为视频文字资产类型。"""
    return str(type_val or "").strip() in VIDEO_TEXT_ASSET_TYPES


def normalize_video_clip_content(raw: Any) -> dict[str, Any]:
    """将任意 content 规范为 VideoClipContent 字典。"""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    tags = raw.get("tags") or []
    if not isinstance(tags, list):
        tags = [str(tags)] if tags else []
    element_refs = raw.get("element_refs") or {}
    if not isinstance(element_refs, dict):
        element_refs = {}
    cleaned_refs: dict[str, list[str]] = {}
    for bucket in ("frame",):
        val = element_refs.get(bucket)
        if val is None:
            continue
        ids = val if isinstance(val, list) else [val]
        cleaned = [str(x).strip() for x in ids if str(x).strip()]
        if cleaned:
            cleaned_refs[bucket] = cleaned
    frame_ids = set(cleaned_refs.get("frame") or [])
    raw_variant_refs = raw.get("variant_refs") or {}
    cleaned_variant_refs: dict[str, str] = {}
    if isinstance(raw_variant_refs, dict):
        for aid, vid in raw_variant_refs.items():
            a = str(aid).strip()
            v = str(vid).strip()
            if a and v and a in frame_ids:
                cleaned_variant_refs[a] = v
    duration = raw.get("duration_sec")
    duration_sec: float | None = None
    if duration is not None and duration != "":
        try:
            duration_sec = float(duration)
        except (TypeError, ValueError):
            duration_sec = None
    mode = str(raw.get("video_mode") or "auto").strip().lower()
    if mode not in ("auto", "text2video", "img2video", "keyframes"):
        mode = "auto"
    model = VideoClipContent(
        summary=str(raw.get("summary") or "").strip(),
        video_prompt=str(raw.get("video_prompt") or raw.get("description") or "").strip(),
        tags=[str(t).strip() for t in tags if str(t).strip()],
        notes=str(raw.get("notes") or "").strip(),
        video_mode=mode,  # type: ignore[arg-type]
        duration_sec=duration_sec,
        camera_motion=str(raw.get("camera_motion") or "").strip(),
        element_refs=cleaned_refs,
        variant_refs=cleaned_variant_refs,
        media_refs=[],
        reference_order=["frame"],
        shot_id=str(raw.get("shot_id") or "").strip(),
        sub_shot_id=str(raw.get("sub_shot_id") or "").strip(),
        prompt_locked=bool(raw.get("prompt_locked")),
        prompt_version=int(raw.get("prompt_version") or 0),
    )
    return model.model_dump()
