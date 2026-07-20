"""共享 EditTimeline + 媒体 fixture（供剪辑/导出单测）。"""

from __future__ import annotations

import pytest

from core.edit.timeline import compile_timeline_from_shots
from core.models.entities import (
    AssetScope,
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    Shot,
    ShotAudioClip,
    ShotAudioTrack,
    ShotSubtitle,
    ShotSubShot,
    TextAsset,
    TextAssetType,
    VideoPlan,
    VideoStyleMode,
)
from core.store.memory import MemoryStore
from core.store.project_paths import media_api_path, relative_media_path, script_media_dir
from tests.support.frame_fixtures import ensure_shot_frame_image
from tests.support.image_text_fixtures import prop_content


@pytest.fixture
def timeline_store(tmp_path, monkeypatch) -> MemoryStore:
    from core.store import project_paths

    monkeypatch.setattr(project_paths, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path / "projects")

    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1", duration_sec=60)
    store.add_script(script)
    char = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="虎",
        content=prop_content(summary="虎", description="东北虎"),
    )
    store.add_text_asset(char)

    media_dir = script_media_dir(project.id, script.id)
    media_dir.mkdir(parents=True, exist_ok=True)
    image_file = media_dir / "img_test.png"
    image_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    api_url = media_api_path(project.id, script.id, "img_test.png")
    media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="虎图",
        url=api_url,
        source_asset_id=char.id,
    )
    store.add_media_asset(media)
    char.primary_media_id = media.id
    store.update_text_asset(char)

    audio_file = media_dir / "tts_test.mp3"
    audio_file.write_bytes(b"ID3")
    audio = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.AUDIO,
        name="配音",
        url=media_api_path(project.id, script.id, "tts_test.mp3"),
    )
    store.add_media_asset(audio)

    shot = Shot(
        order=0,
        duration_ms=3000,
        sub_shots=[
            ShotSubShot(
                start_ms=0,
                end_ms=3000,
                description="老虎在雪原上",
                element_refs={"character": [char.id]},
                camera_motion="ken_burns_in",
            )
        ],
        audio_tracks=[
            ShotAudioTrack(
                kind="voice",
                name="角色音",
                clips=[
                    ShotAudioClip(
                        start_ms=0, end_ms=3000, media_id=audio.id, text="老虎在雪原上"
                    )
                ],
            )
        ],
        subtitles=[ShotSubtitle(start_ms=0, end_ms=3000, text="老虎在雪原上")],
    )
    ensure_shot_frame_image(
        store,
        project_id=project.id,
        script_id=script.id,
        shot=shot,
        image_url=api_url,
    )
    # 关联 TTS 媒体到镜头（供 build_tts_by_shot 反查）
    audio.metadata = {**(audio.metadata or {}), "shot_id": shot.id}
    store.add_media_asset(audio)
    plan = VideoPlan(
        script_id=script.id,
        mode=VideoStyleMode.STORYBOOK,
        shots=[shot],
    )
    store.set_video_plan(plan)
    timeline = compile_timeline_from_shots(
        store,
        script_id=script.id,
        plan=plan,
    )
    store.set_edit_timeline(timeline)
    store._test_project_id = project.id  # type: ignore[attr-defined]
    store._test_script_id = script.id  # type: ignore[attr-defined]
    store._test_audio_id = audio.id  # type: ignore[attr-defined]
    return store
