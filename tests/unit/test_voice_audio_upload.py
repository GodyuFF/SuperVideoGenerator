"""镜内配音音频上传与绑定测试。"""

import io
import struct
import wave

import pytest

from core.assets.voice_audio_upload import ingest_voice_audio_upload
from core.edit.shot_detail_sync import bind_voice_clip_media
from core.models.entities import Project, Script, VideoPlan, VideoStyleMode
from core.store.memory import MemoryStore
from core.store.project_paths import script_media_dir
from core.tts.duration import duration_ms_from_target
from tests.support.shot_fixtures import make_shot


def _minimal_wav_bytes(duration_sec: float = 0.5) -> bytes:
    """生成极短合法 WAV 字节。"""
    sample_rate = 22050
    n_frames = int(sample_rate * duration_sec)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack("<" + "h" * n_frames, *([0] * n_frames)))
    return buf.getvalue()


@pytest.fixture
def voice_upload_ctx(tmp_path, monkeypatch):
    """可写 media 目录的 store + 单镜计划。"""
    monkeypatch.setenv("SVG_DATA_ROOT", str(tmp_path))
    from core.store import project_paths

    project_paths.DATA_ROOT = tmp_path
    project_paths.PROJECTS_ROOT = tmp_path / "projects"

    store = MemoryStore()
    project = Project(title="upload-test")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1", duration_sec=30, content_md="# t")
    store.add_script(script)
    shot = make_shot(order=0, duration_ms=3000, text="你好，世界。")
    plan = VideoPlan(script_id=script.id, mode=VideoStyleMode.STORYBOOK, shots=[shot])
    store.set_video_plan(plan)
    return store, project.id, script.id, shot.id


def test_ingest_voice_audio_upload_generates_cues_and_binds(voice_upload_ctx):
    """上传音频应落盘、写入 subtitle_cues 并绑定 voice clip。"""
    store, project_id, script_id, shot_id = voice_upload_ctx
    wav = _minimal_wav_bytes(0.4)
    media_dir = script_media_dir(project_id, script_id)

    result = ingest_voice_audio_upload(
        store,
        project_id=project_id,
        script_id=script_id,
        shot_id=shot_id,
        file_bytes=wav,
        filename="narration.wav",
        narration_text="你好，世界。",
        bind_clip=True,
    )

    assert result["media_id"]
    assert result["duration_ms"] > 0
    assert result.get("subtitle_cues")
    media_path = media_dir / f"{result['media_id']}.wav"
    assert media_path.is_file()

    plan = store.get_video_plan_for_script(script_id)
    assert plan
    voice = plan.shots[0].audio_tracks[0].clips[0]
    assert voice.media_id == result["media_id"]
    if duration_ms_from_target(media_path) > 0:
        assert len(plan.shots[0].subtitles) >= 1


def test_bind_voice_clip_media_offsets_subtitles(voice_upload_ctx):
    """绑定 media 后句级字幕应写入镜内 subtitles。"""
    store, project_id, script_id, shot_id = voice_upload_ctx
    from core.llm.agent.llm_action import _persist_media
    from core.models.entities import MediaAssetType

    media_dir = script_media_dir(project_id, script_id)
    media_dir.mkdir(parents=True, exist_ok=True)
    path = media_dir / "test_sub.wav"
    path.write_bytes(_minimal_wav_bytes(0.3))

    media = _persist_media(
        store,
        project_id=project_id,
        script_id=script_id,
        media_type=MediaAssetType.AUDIO,
        name="clip",
        url=str(path.resolve()),
        metadata={
            "duration_ms": 2000,
            "subtitle_cues": [
                {"text": "句一", "start_ms": 0, "end_ms": 900},
                {"text": "句二", "start_ms": 900, "end_ms": 2000},
            ],
        },
    )
    out = bind_voice_clip_media(store, script_id, shot_id, media.id)
    plan = store.get_video_plan_for_script(script_id)
    subs = plan.shots[0].subtitles
    assert out["subtitle_count"] == len(subs)
    assert subs[0].text == "句一"
