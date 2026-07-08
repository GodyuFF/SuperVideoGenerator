"""frame 图生图任务收集测试。"""

from core.llm.tools.image.frames import collect_frame_generation_items
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
from tests.support.image_text_fixtures import scene_content


def _ready_scene(store, project, script):
    content = scene_content()
    scene = TextAsset(
        project_id=project.id,
        type=TextAssetType.SCENE,
        scope=AssetScope.PROJECT_SHARED,
        name="空镜",
        content=content,
        source_script_id=script.id,
    )
    store.add_text_asset(scene)
    media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="scene",
        url="https://images.test/scene.png",
        source_asset_id=scene.id,
    )
    store.add_media_asset(media)
    scene.primary_media_id = media.id
    store.update_text_asset(scene)
    return scene, media


def test_collect_frame_items_skips_when_references_not_ready():
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    frame = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.FRAME,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="画面1",
        content={
            "description": "测试画面",
            "element_refs": {"scene": ["scene_missing"]},
            "shot_id": "shot_1",
        },
        source_script_id=script.id,
    )
    store.add_text_asset(frame)
    items = collect_frame_generation_items(store, script.id)
    assert items == []


def test_collect_frame_items_when_references_ready():
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    scene, _ = _ready_scene(store, project, script)
    frame = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.FRAME,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="画面1",
        content={
            "description": "纯空镜镜头",
            "element_refs": {"scene": [scene.id]},
            "shot_id": "shot_1",
        },
        source_script_id=script.id,
    )
    store.add_text_asset(frame)
    items = collect_frame_generation_items(store, script.id)
    assert len(items) == 1
    assert items[0]["asset_type"] == "frame"
    assert len(items[0]["reference_media_ids"]) == 1
