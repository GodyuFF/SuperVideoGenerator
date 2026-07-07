"""EditTimeline 用户 PATCH 服务。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.edit.asset_resolver import validate_edit_timeline
from core.edit.timeline import (
    MAX_VIDEO_LAYERS,
    TRACK_KEYS,
    ensure_video_layers,
    normalize_tracks,
    normalize_video_layers,
    sync_legacy_video_track,
    timeline_board_items,
    timeline_duration_ms,
    validate_timeline_clips,
)
from core.guards.reference import ScriptEditGuard, ScriptEditGuardError
from core.models.entities import EditClip, EditTimeline, EditVideoLayer
from core.store.memory import MemoryStore


class TimelineRevisionError(Exception):
    """乐观锁 revision 冲突。"""

    def __init__(self, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"revision 冲突：期望 {expected}，当前 {actual}")


class TimelineNotFoundError(Exception):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assert_script_editable(store: MemoryStore, script_id: str) -> None:
    script = store.get_script(script_id)
    if script is None:
        raise ValueError("剧本不存在")
    ScriptEditGuard.assert_editable(script)


def timeline_view(store: MemoryStore, timeline: EditTimeline) -> dict[str, Any]:
    board = timeline_board_items(store, timeline)
    board["revision"] = timeline.revision
    board["user_edited"] = timeline.user_edited
    board["last_edited_by"] = timeline.last_edited_by
    board["updated_at"] = timeline.updated_at
    return board


def get_timeline_for_script(store: MemoryStore, script_id: str) -> dict[str, Any] | None:
    timeline = store.get_edit_timeline_for_script(script_id)
    if timeline is None:
        return None
    return timeline_view(store, timeline)


def _mark_user_clip_metadata(clips: list[EditClip]) -> list[EditClip]:
    out: list[EditClip] = []
    for clip in clips:
        meta = dict(clip.metadata or {})
        meta.setdefault("edited_by", "user")
        out.append(clip.model_copy(update={"metadata": meta}))
    return out


def _mark_user_layer_metadata(layers: list[EditVideoLayer]) -> list[EditVideoLayer]:
    out: list[EditVideoLayer] = []
    for layer in layers:
        clips = _mark_user_clip_metadata(layer.clips)
        out.append(layer.model_copy(update={"clips": clips}))
    return out


def patch_timeline(
    store: MemoryStore,
    *,
    script_id: str,
    project_id: str,
    body: dict[str, Any],
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """用户 PATCH 更新剪辑时间轴。"""
    del project_id
    _assert_script_editable(store, script_id)

    timeline = store.get_edit_timeline_for_script(script_id)
    if timeline is None:
        plan = store.get_video_plan_for_script(script_id)
        timeline = EditTimeline(
            script_id=script_id,
            plan_id=plan.id if plan else "",
        )

    if expected_revision is not None and timeline.revision != expected_revision:
        raise TimelineRevisionError(expected_revision, timeline.revision)

    if "video_layers" in body and isinstance(body["video_layers"], list):
        layers = normalize_video_layers(body["video_layers"])
        timeline.video_layers = _mark_user_layer_metadata(layers[:MAX_VIDEO_LAYERS])
        sync_legacy_video_track(timeline)

    if "tracks" in body and isinstance(body["tracks"], dict):
        normalized = normalize_tracks(body["tracks"])
        for key in ("audio", "subtitle"):
            timeline.tracks[key] = _mark_user_clip_metadata(normalized.get(key, []))
        if "video_layers" not in body and normalized.get("video"):
            timeline.video_layers = normalize_video_layers(
                None, legacy_video_clips=_mark_user_clip_metadata(normalized.get("video", []))
            )
            sync_legacy_video_track(timeline)

    if "duration_ms" in body and body["duration_ms"] is not None:
        try:
            timeline.duration_ms = max(0, int(body["duration_ms"]))
        except (TypeError, ValueError):
            pass

    if timeline.duration_ms <= 0:
        timeline.duration_ms = timeline_duration_ms(timeline)

    timeline = ensure_video_layers(timeline)
    sync_legacy_video_track(timeline)

    timeline.revision += 1
    timeline.user_edited = True
    timeline.last_edited_by = "user"
    timeline.updated_at = _now_iso()

    warnings = validate_timeline_clips(timeline)
    store.set_edit_timeline(timeline)

    view = timeline_view(store, timeline)
    view["warnings"] = warnings
    validation = validate_edit_timeline(store, timeline)
    view["validation"] = validation.to_dict()
    return view


def validate_timeline_for_script(store: MemoryStore, script_id: str) -> dict[str, Any]:
    timeline = store.get_edit_timeline_for_script(script_id)
    if timeline is None:
        return {
            "ready": False,
            "warnings": ["尚无剪辑时间轴"],
            "validation": {
                "ready": False,
                "missing_items": [
                    {
                        "category": "timeline",
                        "clip_id": "",
                        "reason": "尚无剪辑计划稿",
                        "suggested_upstream": "storyboard",
                    }
                ],
            },
        }
    warnings = validate_timeline_clips(timeline)
    validation = validate_edit_timeline(store, timeline)
    return {
        "ready": validation.ready,
        "warnings": warnings,
        "validation": validation.to_dict(),
        "timeline_id": timeline.id,
        "revision": timeline.revision,
    }
