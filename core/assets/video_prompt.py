"""video_clip 文字资产视频 Prompt 组装。"""

from __future__ import annotations

from typing import Any

from core.assets.linked_assets_prompt import merge_prompt_with_linked_assets
from core.models.entities import StyleConfig
from core.models.video_text_asset import normalize_video_clip_content
from core.store.memory import MemoryStore


def compose_video_clip_prompt(
    content: dict[str, Any],
    *,
    store: MemoryStore | None = None,
    project_style: StyleConfig | None = None,
) -> str:
    """从 video_clip content 组装生视频 prompt，并拼接关联资产动态上下文。"""
    normalized = normalize_video_clip_content(content)
    parts: list[str] = []
    vp = str(normalized.get("video_prompt") or "").strip()
    if vp:
        parts.append(vp)
    summary = str(normalized.get("summary") or "").strip()
    if summary and summary not in vp:
        parts.append(summary)
    motion = str(normalized.get("camera_motion") or "").strip()
    if motion and motion != "static":
        parts.append(f"camera: {motion}")
    if project_style and str(getattr(project_style, "aspect_ratio", "") or "").strip():
        parts.append(f"画幅 {project_style.aspect_ratio}")
    base = "，".join(p for p in parts if p).strip()
    if not base:
        base = "自然动态画面，电影感光照与运镜"
    return merge_prompt_with_linked_assets(base, store, normalized)
