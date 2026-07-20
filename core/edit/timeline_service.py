"""EditTimeline 用户 PATCH 服务。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.edit.asset_resolver import validate_edit_timeline
from core.edit.timeline import (
    AUDIO_SUBTITLE_KEYS,
    MAX_VIDEO_LAYERS,
    TRACK_KEYS,
    extract_agent_video_clips,
    normalize_tracks,
    normalize_video_layers,
    resolve_agent_video_layers,
    sync_timeline_duration_ms,
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


def empty_timeline_view(*, editable: bool) -> dict[str, Any]:
    """尚未生成剪辑时间轴时的空视图（供 GET API 返回 200）。"""
    return {
        "timeline_id": "",
        "plan_id": "",
        "duration_ms": 0,
        "revision": 0,
        "user_edited": False,
        "last_edited_by": "",
        "updated_at": "",
        "metadata": {},
        "tracks": {key: [] for key in TRACK_KEYS},
        "video_layers": [],
        "editable": editable,
    }


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


def _sync_video_plan_from_timeline(
    store: MemoryStore, script_id: str, timeline: EditTimeline
) -> None:
    """OpenCut 用户 PATCH 后将时间轴手改回写镜内 Shot 结构。"""
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return
    from core.edit.shot_flatten import apply_timeline_edits_to_shots

    updated = apply_timeline_edits_to_shots(list(plan.shots), timeline)
    store.set_video_plan(plan.model_copy(update={"shots": updated}))


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

    if "tracks" in body and isinstance(body["tracks"], dict):
        normalized = normalize_tracks(body["tracks"])
        for key in AUDIO_SUBTITLE_KEYS:
            timeline.tracks[key] = _mark_user_clip_metadata(normalized.get(key, []))
        if "video_layers" not in body:
            agent_video = extract_agent_video_clips(body["tracks"])
            if agent_video:
                timeline.video_layers = _mark_user_layer_metadata(
                    resolve_agent_video_layers(None, _mark_user_clip_metadata(agent_video))
                )

    if "duration_ms" in body and body["duration_ms"] is not None:
        try:
            timeline.duration_ms = max(0, int(body["duration_ms"]))
        except (TypeError, ValueError):
            pass

    if "metadata" in body and isinstance(body["metadata"], dict):
        merged = dict(timeline.metadata or {})
        merged.update(body["metadata"])
        timeline.metadata = merged

    if timeline.duration_ms <= 0:
        timeline.duration_ms = timeline_duration_ms(timeline)
    else:
        timeline = sync_timeline_duration_ms(timeline)

    timeline.revision += 1
    timeline.user_edited = True
    timeline.last_edited_by = "user"
    timeline.updated_at = _now_iso()

    warnings = validate_timeline_clips(timeline)
    store.set_edit_timeline(timeline)
    _sync_video_plan_from_timeline(store, script_id, timeline)

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
