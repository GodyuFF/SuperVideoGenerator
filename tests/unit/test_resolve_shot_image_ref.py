"""resolve_shot_image_ref 优先 frame、禁止 character 裸图回退。"""

from core.edit.timeline import resolve_shot_image_ref
from core.models.entities import (
    AssetScope,
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    TextAsset,
    TextAssetType,
    VideoPlanShot,
)
from core.store.memory import MemoryStore
from tests.support.image_text_fixtures import character_content


def test_resolve_prefers_frame_over_character():
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)

    char = TextAsset(
        project_id=project.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.PROJECT_SHARED,
        name="角色",
        content=character_content(),
        source_script_id=script.id,
    )
    store.add_text_asset(char)
    char_media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="char_green",
        url="https://images.test/char.png",
        source_asset_id=char.id,
    )
    store.add_media_asset(char_media)
    char.primary_media_id = char_media.id
    store.update_text_asset(char)

    frame = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.FRAME,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="画面",
        content={"description": "合成画面", "shot_id": "shot_x"},
        source_script_id=script.id,
    )
    store.add_text_asset(frame)
    frame_media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="frame",
        url="https://images.test/frame.png",
        source_asset_id=frame.id,
    )
    store.add_media_asset(frame_media)
    frame.primary_media_id = frame_media.id
    store.update_text_asset(frame)

    shot = VideoPlanShot(
        narration_text="镜头",
        asset_refs={
            "frame": [frame.id],
            "character": [char.id],
        },
    )
    assert resolve_shot_image_ref(store, shot) == frame_media.id


def test_resolve_does_not_fallback_to_character():
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)

    char = TextAsset(
        project_id=project.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.PROJECT_SHARED,
        name="角色",
        content=character_content(),
        source_script_id=script.id,
    )
    store.add_text_asset(char)
    char_media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="char",
        url="https://images.test/char.png",
        source_asset_id=char.id,
    )
    store.add_media_asset(char_media)
    char.primary_media_id = char_media.id
    store.update_text_asset(char)

    shot = VideoPlanShot(
        narration_text="镜头",
        asset_refs={"character": [char.id]},
    )
    assert resolve_shot_image_ref(store, shot) is None
