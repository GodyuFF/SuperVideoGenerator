"""绿幕抠图与 persist 集成测试。"""

from pathlib import Path
from unittest.mock import patch

import pytest

from core.assets.chroma_key import (
    apply_chroma_key_to_media,
    is_chroma_eligible_text_type,
    reapply_chroma_for_script,
)
from core.llm.agent.llm_action import persist_single_generated_image
from core.llm.agent.react_core import AgentRunContext
from core.models.entities import (
    AssetScope,
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    TextAsset,
    TextAssetType,
)
from core.models.image_text_asset import normalize_image_text_content
from core.store.media_storage import persist_media_url_to_disk
from core.store.project_paths import script_media_dir
from core.tts.ffmpeg_util import is_ffmpeg_available
from tests.support.image_text_fixtures import character_content


@pytest.fixture
def chroma_store(tmp_path, monkeypatch):
    from core.store import project_paths

    monkeypatch.setattr(project_paths, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path / "projects")

    store = __import__("core.store.memory", fromlist=["MemoryStore"]).MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    char = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="主角",
        content=normalize_image_text_content(
            TextAssetType.CHARACTER, character_content(summary="主角")
        ),
    )
    store.add_text_asset(char)
    store._pid = project.id  # type: ignore[attr-defined]
    store._sid = script.id  # type: ignore[attr-defined]
    store._cid = char.id  # type: ignore[attr-defined]
    return store


def test_is_chroma_eligible_text_type():
    assert is_chroma_eligible_text_type(TextAssetType.CHARACTER) is True
    assert is_chroma_eligible_text_type(TextAssetType.PROP) is True
    assert is_chroma_eligible_text_type(TextAssetType.SCENE) is False


def test_persist_character_invokes_chroma(chroma_store, tmp_path):
    project_id = chroma_store._pid  # type: ignore[attr-defined]
    script_id = chroma_store._sid  # type: ignore[attr-defined]
    char_id = chroma_store._cid  # type: ignore[attr-defined]

    media_dir = script_media_dir(project_id, script_id)
    media_dir.mkdir(parents=True, exist_ok=True)
    green = media_dir / "green.png"
    green.write_bytes(b"fake")

    def _fake_disk(**kwargs):
        dest = media_dir / f"{kwargs['media_id']}.png"
        dest.write_bytes(green.read_bytes())
        return f"projects/{project_id}/scripts/{script_id}/assets/media/{dest.name}"

    ctx = AgentRunContext(
        task_brief="",
        work_context={"script_id": script_id, "project_id": project_id},
        script_id=script_id,
        step_id="t",
        agent_name="image_agent",
        project_id=project_id,
    )

    with patch(
        "core.store.media_storage.persist_media_url_to_disk",
        side_effect=_fake_disk,
    ), patch(
        "core.assets.chroma_key.apply_chroma_key_to_media",
        return_value=True,
    ) as chroma_mock, patch(
        "core.llm.agent.llm_action.schedule_save",
    ) as save_mock:
        media = persist_single_generated_image(
            chroma_store,
            ctx,
            {
                "url": "https://images.test/generated/base.png",
                "source_text_asset_id": char_id,
                "name": "主角",
            },
        )

    assert media is not None
    chroma_mock.assert_called_once()
    save_mock.assert_called_once()


@pytest.mark.skipif(not is_ffmpeg_available(), reason="FFmpeg 不可用")
def test_reapply_chroma_for_script_integration(chroma_store, tmp_path):
    from tests.unit.test_chroma_key import _write_green_with_red_square

    project_id = chroma_store._pid  # type: ignore[attr-defined]
    script_id = chroma_store._sid  # type: ignore[attr-defined]
    char_id = chroma_store._cid  # type: ignore[attr-defined]

    media_dir = script_media_dir(project_id, script_id)
    media_dir.mkdir(parents=True, exist_ok=True)
    src = media_dir / "media_test1.png"
    _write_green_with_red_square(src)

    rel = persist_media_url_to_disk(
        project_id=project_id,
        script_id=script_id,
        media_id="media_test1",
        url=str(src),
        media_type="image",
    )
    media = MediaAsset(
        id="media_test1",
        project_id=project_id,
        script_id=script_id,
        type=MediaAssetType.IMAGE,
        name="主角图",
        url=rel,
        source_asset_id=char_id,
        metadata={"chroma_key_applied": False},
    )
    chroma_store.add_media_asset(media)

    result = reapply_chroma_for_script(
        chroma_store,
        project_id=project_id,
        script_id=script_id,
    )
    assert result["applied_count"] == 1
    updated = chroma_store.media_assets["media_test1"]
    assert updated.metadata.get("chroma_key_applied") is True
    assert updated.url.endswith(".png")
    assert (media_dir / "media_test1.png").is_file()
