"""EditTimeline TTS 映射单元测试。"""

import pytest

from core.edit.timeline import build_tts_by_shot, compile_timeline_from_shots
from core.models.entities import (
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    ShotAudioClip,
    ShotAudioTrack,
    VideoPlan,
    new_id,
)
from core.store.memory import MemoryStore
from tests.support.shot_fixtures import make_shot


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


def test_build_tts_by_shot_skips_superseded_and_prefers_voice_clip(
    store, script, monkeypatch, tmp_path
):
    """映射应跳过 superseded 资产，并优先使用镜内 voice clip 绑定的 media。"""
    from core.store import project_paths

    script_id = script.id
    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path / "projects")
    media_dir = project_paths.script_media_dir(script.project_id, script_id)
    media_dir.mkdir(parents=True, exist_ok=True)
    (media_dir / "audio_clip.mp3").write_bytes(b"ID3fake")
    (media_dir / "audio_store.mp3").write_bytes(b"ID3fake")

    shot = make_shot(order=0, duration_ms=3000, text="旁白").model_copy(update={"id": "shot_1"})
    shot = shot.model_copy(
        update={
            "audio_tracks": [
                ShotAudioTrack(
                    kind="voice",
                    name="角色音",
                    clips=[
                        ShotAudioClip(
                            start_ms=0,
                            end_ms=3000,
                            text="旁白",
                            media_id="audio_clip",
                        )
                    ],
                )
            ]
        }
    )
    plan = VideoPlan(id=new_id("plan"), script_id=script_id, shots=[shot])
    store.video_plans[plan.id] = plan

    rel_clip = project_paths.relative_media_path(
        script.project_id, script_id, "audio_clip.mp3"
    )
    rel_store = project_paths.relative_media_path(
        script.project_id, script_id, "audio_store.mp3"
    )
    store.add_media_asset(
        MediaAsset(
            id="audio_old",
            project_id=script.project_id,
            script_id=script_id,
            type=MediaAssetType.AUDIO,
            name="n1",
            url=rel_store,
            metadata={"shot_id": "shot_1", "superseded": True},
        )
    )
    store.add_media_asset(
        MediaAsset(
            id="audio_store",
            project_id=script.project_id,
            script_id=script_id,
            type=MediaAssetType.AUDIO,
            name="n1",
            url=rel_store,
            metadata={"shot_id": "shot_1"},
        )
    )
    store.add_media_asset(
        MediaAsset(
            id="audio_clip",
            project_id=script.project_id,
            script_id=script_id,
            type=MediaAssetType.AUDIO,
            name="n1",
            url=rel_clip,
            metadata={"shot_id": "shot_1"},
        )
    )

    mapping = build_tts_by_shot(store, script_id)
    assert mapping["shot_1"] == "audio_clip"


def test_compile_timeline_uses_bound_voice_clip_duration(store, script):
    """镜内 voice clip 已绑定 media 时，投影音频轨应覆盖 clip 跨度。"""
    script_id = script.id
    shot = make_shot(order=0, duration_ms=2000, text="旁白").model_copy(
        update={"id": "shot_1"}
    )
    audio_id = "audio_long"
    shot = shot.model_copy(
        update={
            "audio_tracks": [
                ShotAudioTrack(
                    kind="voice",
                    name="角色音",
                    clips=[
                        ShotAudioClip(
                            start_ms=0,
                            end_ms=5000,
                            text="旁白",
                            media_id=audio_id,
                        )
                    ],
                )
            ],
            "duration_ms": 5000,
        }
    )
    plan = VideoPlan(id=new_id("plan"), script_id=script_id, shots=[shot])
    store.video_plans[plan.id] = plan
    store.add_media_asset(
        MediaAsset(
            id=audio_id,
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
    assert audio.end_ms - audio.start_ms == 5000
