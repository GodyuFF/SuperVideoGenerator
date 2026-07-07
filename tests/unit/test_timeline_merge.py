"""merge_agent_timeline 单元测试。"""

from core.edit.timeline import merge_agent_timeline, normalize_tracks
from core.models.entities import EditClip, EditTimeline


def _clip(clip_id: str, track: str, start: int, end: int, *, edited_by: str = "") -> EditClip:
    meta = {"edited_by": edited_by} if edited_by else {}
    return EditClip(
        id=clip_id,
        track=track,  # type: ignore[arg-type]
        start_ms=start,
        end_ms=end,
        label=clip_id,
        metadata=meta,
    )


def test_merge_preserves_user_clips():
    existing = EditTimeline(
        script_id="s1",
        plan_id="vp1",
        user_edited=True,
        tracks={
            "video": [_clip("u1", "video", 0, 3000, edited_by="user")],
            "audio": [],
            "subtitle": [],
        },
    )
    agent_tracks = normalize_tracks(
        {
            "video": [
                {
                    "id": "a1",
                    "track": "video",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "label": "a1",
                    "metadata": {"edited_by": "agent"},
                }
            ],
            "audio": [],
            "subtitle": [],
        }
    )
    merged = merge_agent_timeline(
        existing,
        agent_tracks,
        script_id="s1",
        plan_id="vp1",
        mode="merge",
    )
    ids = [c.id for c in merged.tracks["video"]]
    assert "u1" in ids
    assert "a1" in ids


def test_merge_replace_overwrites():
    existing = EditTimeline(
        script_id="s1",
        plan_id="vp1",
        user_edited=True,
        tracks={
            "video": [_clip("u1", "video", 0, 3000, edited_by="user")],
            "audio": [],
            "subtitle": [],
        },
    )
    agent_tracks = normalize_tracks(
        {
            "video": [
                {
                    "id": "a1",
                    "track": "video",
                    "start_ms": 0,
                    "end_ms": 4000,
                    "label": "a1",
                }
            ],
            "audio": [],
            "subtitle": [],
        }
    )
    merged = merge_agent_timeline(
        existing,
        agent_tracks,
        script_id="s1",
        plan_id="vp1",
        mode="replace",
    )
    assert [c.id for c in merged.tracks["video"]] == ["a1"]
