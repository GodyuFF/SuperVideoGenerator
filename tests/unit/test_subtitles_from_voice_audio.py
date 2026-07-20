"""从配音音频构建字幕预览测试。"""

from __future__ import annotations

from core.edit.shot_detail_sync import build_shot_subtitles_from_voice_audio
from core.models.entities import (
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    ShotAudioClip,
    ShotAudioTrack,
    ShotSubShot,
    VideoPlan,
    VideoStyleMode,
)
from core.store.memory import MemoryStore
from tests.support.shot_fixtures import make_shot


def test_build_shot_subtitles_from_voice_audio_uses_media_cues_not_clip_text() -> None:
    """字幕文本来自 media.subtitle_cues，即使配音幕文案不同。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    audio = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.AUDIO,
        name="voice",
        url="https://audio.test/a.mp3",
        metadata={
            "duration_ms": 4000,
            "narration_text": "真实旁白。第二句。",
            "subtitle_cues": [
                {"text": "真实旁白。", "start_ms": 0, "end_ms": 2000, "source": "edge"},
                {"text": "第二句。", "start_ms": 2000, "end_ms": 4000, "source": "edge"},
            ],
        },
    )
    store.add_media_asset(audio)
    shot = make_shot(order=0, duration_ms=4000, text="过期文案不应出现")
    shot = shot.model_copy(
        update={
            "sub_shots": [
                ShotSubShot(id="ssb1", start_ms=0, end_ms=4000, description="x")
            ],
            "audio_tracks": [
                ShotAudioTrack(
                    kind="voice",
                    clips=[
                        ShotAudioClip(
                            id="sac1",
                            start_ms=0,
                            end_ms=4000,
                            text="过期文案不应出现",
                            character_ref="txt_hero",
                            media_id=audio.id,
                        )
                    ],
                )
            ],
            "subtitles": [],
        }
    )
    store.set_video_plan(
        VideoPlan(script_id=script.id, mode=VideoStyleMode.STORYBOOK, shots=[shot])
    )

    rows = build_shot_subtitles_from_voice_audio(store, script.id, shot.id)
    assert len(rows) == 2
    assert rows[0]["text"] == "真实旁白。"
    assert rows[1]["text"] == "第二句。"
    assert "过期" not in rows[0]["text"]
    assert rows[0]["character"] == "txt_hero"
    assert rows[0]["end_ms"] == 2000


def test_build_shot_subtitles_empty_without_bound_media() -> None:
    """无绑定配音 media 时返回空列表。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    shot = make_shot(order=0, text="仅文案")
    store.set_video_plan(
        VideoPlan(script_id=script.id, mode=VideoStyleMode.STORYBOOK, shots=[shot])
    )
    assert build_shot_subtitles_from_voice_audio(store, script.id, shot.id) == []
