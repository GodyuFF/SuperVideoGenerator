"""剪辑 capabilities.json 单源加载与校验。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


def capabilities_path() -> Path:
    return _repo_root() / "core" / "edit" / "capabilities.json"


@lru_cache(maxsize=1)
def load_edit_capability_defs() -> dict[str, Any]:
    path = capabilities_path()
    if not path.is_file():
        return {
            "motions": [],
            "motion_aliases": {},
            "transitions": [],
            "backgrounds": [],
            "transition_max_duration_ms": 2000,
        }
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def load_edit_capabilities() -> dict[str, Any]:
    """剪辑能力单源（运镜/转场/背景 + FFmpeg 导出可用性）。"""
    from core.edit.export_settings import get_export_manager
    from core.edit.timeline import MAX_VIDEO_LAYERS

    caps = dict(load_edit_capability_defs())
    caps.update(get_export_manager().get_public_config())
    caps["max_video_layers"] = MAX_VIDEO_LAYERS
    caps["nle_export_enabled"] = True
    caps["nle_export_formats"] = ["premiere"]
    return caps


def known_motions() -> frozenset[str]:
    caps = load_edit_capability_defs()
    motions = set(caps.get("motions") or [])
    motions.update((caps.get("motion_aliases") or {}).keys())
    motions.update((caps.get("motion_aliases") or {}).values())
    return frozenset(str(m) for m in motions)


def resolve_motion(motion: str | None) -> str:
    """别名解析 + 回落到合法 preset。"""
    caps = load_edit_capability_defs()
    raw = (motion or "ken_burns_in").strip().lower()
    aliases = caps.get("motion_aliases") or {}
    if raw in aliases:
        raw = str(aliases[raw]).lower()
    motions = caps.get("motions") or []
    if raw in motions:
        return raw
    if motions:
        return str(motions[0])
    return "ken_burns_in"


def normalize_motion(motion: str | None) -> str:
    return resolve_motion(motion)


def validate_transition_type(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip().lower()
    transitions = load_edit_capability_defs().get("transitions") or []
    if raw in transitions:
        return raw
    return None


def validate_background_type(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip().lower()
    backgrounds = load_edit_capability_defs().get("backgrounds") or []
    if raw in backgrounds:
        return raw
    return None


def transition_max_duration_ms() -> int:
    return int(load_edit_capability_defs().get("transition_max_duration_ms") or 2000)


def edit_capability_issues(timeline) -> list[tuple[str, str, str]]:
    """返回 (clip_id, field, reason) 列表；空表示能力范围内。"""
    from core.edit.timeline import ensure_video_layers

    issues: list[tuple[str, str, str]] = []
    caps = load_edit_capability_defs()
    motions = set(caps.get("motions") or [])

    timeline = ensure_video_layers(timeline)
    if timeline.video_layers:
        video_clips = [clip for layer in timeline.video_layers for clip in layer.clips]
    else:
        video_clips = list(timeline.tracks.get("video", []))

    seen: set[str] = set()
    for clip in video_clips:
        if clip.id in seen:
            continue
        seen.add(clip.id)
        if clip.motion:
            if resolve_motion(clip.motion) not in motions:
                issues.append((clip.id, "motion", f"不支持的运镜：{clip.motion}"))

        if clip.motion_detail and clip.motion_detail.type:
            if resolve_motion(clip.motion_detail.type) not in motions:
                issues.append(
                    (clip.id, "motion_detail.type", f"不支持的运镜：{clip.motion_detail.type}")
                )

        for field_name, tr in (
            ("transition_in", clip.transition_in),
            ("transition_out", clip.transition_out),
        ):
            if tr is None:
                continue
            if validate_transition_type(tr.type) is None:
                issues.append((clip.id, field_name, f"不支持的转场：{tr.type}"))
            elif int(tr.duration_ms) > transition_max_duration_ms():
                issues.append(
                    (
                        clip.id,
                        field_name,
                        f"转场时长超过上限 {transition_max_duration_ms()}ms",
                    )
                )

        if clip.background and validate_background_type(clip.background.type) is None:
            issues.append(
                (clip.id, "background.type", f"不支持的背景：{clip.background.type}")
            )

    return issues
