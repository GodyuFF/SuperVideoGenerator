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
    TextAsset,
    TextAssetType,
    VideoPlan,
    VideoPlanShot,
    VideoStyleMode,
)
from core.store.memory import MemoryStore
from core.store.project_paths import media_api_path, relative_media_path, script_media_dir
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

    plan = VideoPlan(
        script_id=script.id,
        mode=VideoStyleMode.DYNAMIC_IMAGE,
        shots=[
            VideoPlanShot(
                order=0,
                duration_ms=3000,
                narration_text="老虎在雪原上",
                camera_motion="ken_burns_in",
                asset_refs={"character": [char.id]},
            )
        ],
    )
    store.set_video_plan(plan)
    timeline = compile_timeline_from_shots(
        store,
        script_id=script.id,
        plan=plan,
        tts_by_shot={plan.shots[0].id: audio.id},
    )
    store.set_edit_timeline(timeline)
    store._test_project_id = project.id  # type: ignore[attr-defined]
    store._test_script_id = script.id  # type: ignore[attr-defined]
    store._test_audio_id = audio.id  # type: ignore[attr-defined]
    return store
