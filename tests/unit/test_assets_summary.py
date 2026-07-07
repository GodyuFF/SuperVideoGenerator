"""tool_list_assets / build_script_assets_payload 测试。"""

import json

import pytest

from core.llm.master.tools import MasterToolExecutor
from core.llm.tools.shared.assets_summary import build_script_assets_payload
from core.models.entities import (
    AssetScope,
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    TextAsset,
    TextAssetType,
)
from core.store.memory import MemoryStore
from core.store.project_paths import media_api_path, relative_media_path
from tests.support.image_text_fixtures import character_content


@pytest.fixture
def asset_store(tmp_path, monkeypatch) -> tuple[MemoryStore, str]:
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
        content=character_content(summary="虎"),
    )
    store.add_text_asset(char)

    media_dir = project_paths.script_media_dir(project.id, script.id)
    media_dir.mkdir(parents=True, exist_ok=True)
    image_file = media_dir / "img_test.png"
    image_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    image = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="虎图",
        url=media_api_path(project.id, script.id, "img_test.png"),
        source_asset_id=char.id,
    )
    store.add_media_asset(image)
    char.primary_media_id = image.id
    store.update_text_asset(char)

    audio = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.AUDIO,
        name="配音",
        url=media_api_path(project.id, script.id, "tts_test.mp3"),
    )
    store.add_media_asset(audio)

    return store, script.id


def test_build_script_assets_payload_includes_media(asset_store):
    store, script_id = asset_store
    payload = build_script_assets_payload(store, script_id)

    assert payload["script"]["title"] == "s1"
    assert payload["summary"]["text_asset_count"] == 1
    assert payload["summary"]["media_counts"]["image"] == 1
    assert payload["summary"]["media_counts"]["audio"] == 1

    images = payload["media"]["image"]["items"]
    assert len(images) == 1
    assert images[0]["name"] == "虎图"
    assert images[0]["link"].startswith("/api/projects/")
    assert images[0]["is_accessible"] is True
    assert images[0]["source_asset_name"] == "虎"

    char = next(a for a in payload["text_assets"] if a["type"] == "character")
    assert char["linked_media"][0]["id"] == images[0]["id"]
    assert char["linked_media"][0]["link"] == images[0]["link"]


@pytest.mark.asyncio
async def test_master_tool_list_assets_returns_json(asset_store):
    store, script_id = asset_store
    executor = MasterToolExecutor(store)
    result = await executor.execute("tool_list_assets", script_id)
    payload = json.loads(result)
    assert payload["media"]["audio"]["count"] == 1
    assert payload["text_assets"][0]["linked_media"]
