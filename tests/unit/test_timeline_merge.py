"""merge_agent_timeline 单元测试。"""

from core.edit.timeline import (
    extract_agent_video_clips,
    flat_video_clips,
    merge_agent_timeline,
    normalize_tracks,
    video_layers_from_agent_clips,
)
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


def _timeline_with_video(
    clips: list[EditClip],
    *,
    user_edited: bool = False,
) -> EditTimeline:
    """构建含 video_layers 的测试时间轴。"""
    return EditTimeline(
        script_id="s1",
        plan_id="vp1",
        user_edited=user_edited,
        tracks={"audio": [], "subtitle": []},
        video_layers=video_layers_from_agent_clips(clips),
    )


def test_merge_preserves_user_clips():
    existing = _timeline_with_video(
        [_clip("u1", "video", 0, 3000, edited_by="user")],
        user_edited=True,
    )
    raw = {
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
    agent_tracks = normalize_tracks(raw)
    agent_video = extract_agent_video_clips(raw)
    merged = merge_agent_timeline(
        existing,
        {**agent_tracks, "video": agent_video},
        script_id="s1",
        plan_id="vp1",
        mode="merge",
    )
    ids = [c.id for c in flat_video_clips(merged)]
    assert "u1" in ids
    assert "a1" in ids


def test_merge_replace_overwrites():
    existing = _timeline_with_video(
        [_clip("u1", "video", 0, 3000, edited_by="user")],
        user_edited=True,
    )
    raw = {
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
    agent_tracks = normalize_tracks(raw)
    agent_video = extract_agent_video_clips(raw)
    merged = merge_agent_timeline(
        existing,
        {**agent_tracks, "video": agent_video},
        script_id="s1",
        plan_id="vp1",
        mode="replace",
    )
    assert [c.id for c in flat_video_clips(merged)] == ["a1"]
