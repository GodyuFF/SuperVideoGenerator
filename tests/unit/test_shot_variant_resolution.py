"""分镜 variant_refs / frame 选图测试。"""

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
from core.models.image_text_asset import (
    ensure_image_variants,
    get_base_variant,
    merge_incoming_variants,
    normalize_image_text_content,
    parse_image_variants,
    update_variant_in_content,
)
from core.store.memory import MemoryStore
from tests.support.image_text_fixtures import character_content


def test_resolve_shot_uses_frame_not_character_variant():
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    content = normalize_image_text_content(TextAssetType.CHARACTER, character_content())
    content = merge_incoming_variants(
        content,
        [{"kind": "expression", "label": "怒", "variant_prompt": "愤怒"}],
    )
    char = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="角色",
        content=content,
    )
    store.add_text_asset(char)
    base_media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="base",
        url="https://images.test/base.png",
        source_asset_id=char.id,
    )
    expr_media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="angry",
        url="https://images.test/angry.png",
        source_asset_id=char.id,
    )
    store.add_media_asset(base_media)
    store.add_media_asset(expr_media)
    content = ensure_image_variants(content)
    base = get_base_variant(content)
    assert base
    expr_v = [v for v in parse_image_variants(content) if v.kind == "expression"][0]
    content = update_variant_in_content(content, base.id, media_id=base_media.id)
    content = update_variant_in_content(content, expr_v.id, media_id=expr_media.id)
    char.content = content
    char.primary_media_id = base_media.id
    store.update_text_asset(char)

    frame = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.FRAME,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="画面",
        content={
            "description": "角色愤怒表情的中景",
            "element_refs": {"character": [char.id]},
            "shot_id": "shot_1",
        },
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
        asset_refs={"frame": [frame.id], "character": [char.id]},
        variant_refs={char.id: expr_v.id},
    )
    mid = resolve_shot_image_ref(store, shot)
    assert mid == frame_media.id
