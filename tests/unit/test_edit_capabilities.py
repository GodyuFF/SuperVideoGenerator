"""edit_capabilities 运镜别名与校验测试。"""

from core.edit.edit_capabilities import (
    edit_capability_issues,
    load_edit_capability_defs,
    resolve_motion,
)
from core.edit.timeline import normalize_tracks
from core.models.entities import EditTimeline


def test_resolve_motion_aliases():
    load_edit_capability_defs.cache_clear()
    assert resolve_motion("gentle_push_in") == "ken_burns_in"
    assert resolve_motion("slow_pan_right") == "pan_right"
    assert resolve_motion("slow_zoom_in") == "ken_burns_in"
    assert resolve_motion("unknown_motion_xyz") == "ken_burns_in"


def test_edit_capability_issues_accepts_aliases():
    load_edit_capability_defs.cache_clear()
    timeline = EditTimeline(
        script_id="scr_test",
        duration_ms=3000,
        tracks=normalize_tracks(
            {
                "video": [
                    {
                        "track": "video",
                        "start_ms": 0,
                        "end_ms": 3000,
                        "motion": "gentle_push_in",
                        "motion_detail": {"type": "slow_pan_right"},
                    }
                ],
                "audio": [],
                "subtitle": [],
            }
        ),
    )
    issues = edit_capability_issues(timeline)
    assert issues == []


def test_normalize_tracks_resolves_motion_on_parse():
    load_edit_capability_defs.cache_clear()
    tracks = normalize_tracks(
        {
            "video": [
                {
                    "track": "video",
                    "start_ms": 0,
                    "end_ms": 2000,
                    "motion": "gentle_push_in",
                }
            ],
            "audio": [],
            "subtitle": [],
        }
    )
    assert tracks["video"][0].motion == "ken_burns_in"
