"""extract_narration 单元测试。"""

import pytest

from core.llm.tools.tts.extract import build_narration_payload, format_narration_observation
from core.models.entities import VideoPlan, VideoPlanShot, new_id
from core.store.memory import MemoryStore


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


def test_build_narration_payload_from_plan(store):
    script_id = "script_tts_extract"
    plan = VideoPlan(
        id=new_id("plan"),
        script_id=script_id,
        shots=[
            VideoPlanShot(
                id="shot_a",
                order=0,
                duration_ms=3000,
                narration_text="第一句旁白",
            ),
            VideoPlanShot(
                id="shot_b",
                order=1,
                duration_ms=2000,
                narration_text="",
            ),
            VideoPlanShot(
                id="shot_c",
                order=2,
                duration_ms=4000,
                narration_text="第三句旁白",
            ),
        ],
    )
    store.video_plans[plan.id] = plan

    payload = build_narration_payload(store, script_id)
    assert payload["valid"] is True
    assert payload["line_count"] == 2
    assert len(payload["items"]) == 2
    assert payload["items"][0]["shot_id"] == "shot_a"
    obs = format_narration_observation(payload)
    assert "2" in obs


def test_build_narration_payload_missing_plan(store):
    payload = build_narration_payload(store, "missing_script")
    assert payload["valid"] is False
    assert payload["line_count"] == 0
