"""EditTimeline TTS 映射单元测试。"""

import pytest

from core.edit.timeline import build_tts_by_shot, compile_timeline_from_shots
from core.models.entities import (
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    VideoPlan,
    VideoPlanShot,
    new_id,
)
from core.store.memory import MemoryStore


@pytest.fixture
def store() -> MemoryStore:
    s = MemoryStore()
    project = Project(title="p")
    s.add_project(project)
    script = Script(project_id=project.id, title="s1", duration_sec=60)
    s.add_script(script)
    return s


@pytest.fixture
def script(store: MemoryStore) -> Script:
    return next(iter(store.scripts.values()))


def test_build_tts_by_shot(store, script):
    script_id = script.id
    store.add_media_asset(
        MediaAsset(
            id="audio_1",
            project_id=script.project_id,
            script_id=script_id,
            type=MediaAssetType.AUDIO,
            name="n1",
            url="projects/p/s/assets/media/a.mp3",
            metadata={"shot_id": "shot_x"},
        )
    )
    mapping = build_tts_by_shot(store, script_id)
    assert mapping["shot_x"] == "audio_1"


def test_compile_timeline_uses_tts_duration(store, script):
    script_id = script.id
    plan = VideoPlan(
        id=new_id("plan"),
        script_id=script_id,
        shots=[
            VideoPlanShot(
                id="shot_1",
                order=0,
                duration_ms=2000,
                narration_text="旁白",
            ),
        ],
    )
    store.video_plans[plan.id] = plan
    store.add_media_asset(
        MediaAsset(
            id="audio_long",
            project_id=script.project_id,
            script_id=script_id,
            type=MediaAssetType.AUDIO,
            name="n1",
            url="projects/p/s/assets/media/a.mp3",
            metadata={"shot_id": "shot_1", "duration_ms": 5000},
        )
    )
    timeline = compile_timeline_from_shots(store, script_id=script_id, plan=plan)
    audio = timeline.tracks["audio"][0]
    assert audio.end_ms - audio.start_ms >= 5000
