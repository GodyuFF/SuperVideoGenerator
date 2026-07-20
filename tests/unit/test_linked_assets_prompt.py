"""关联资产动态提示词：生图/生视频辅助上下文。"""

from __future__ import annotations

from core.assets.linked_assets_prompt import (
    build_linked_assets_aux_prompt,
    merge_prompt_with_linked_assets,
)
from core.assets.video_prompt import compose_video_clip_prompt
from core.llm.tools.image.frames import resolve_frame_generation_prompt
from core.models.entities import (
    AssetScope,
    Project,
    Script,
    TextAsset,
    TextAssetType,
)
from core.store.memory import MemoryStore


def _store_with_linked() -> tuple[MemoryStore, dict[str, list[str]]]:
    """构建含角色/空镜的 store 与 element_refs。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    scene = TextAsset(
        project_id=project.id,
        type=TextAssetType.SCENE,
        scope=AssetScope.PROJECT_SHARED,
        name="夕阳蜂巢入口",
        content={"summary": "橙金色蜂巢入口", "description": "巨大六角蜂巢镶嵌在山壁，夕阳洒落"},
        source_script_id=script.id,
    )
    character = TextAsset(
        project_id=project.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.PROJECT_SHARED,
        name="女娲",
        content={
            "summary": "创世女神",
            "description": "长发与华贵长袍的女神",
            "costume": "绯色长袍",
            "distinctive_features": "额间金纹",
        },
        source_script_id=script.id,
    )
    store.add_text_asset(scene)
    store.add_text_asset(character)
    refs = {"scene": [scene.id], "character": [character.id]}
    return store, refs


def test_build_linked_assets_aux_prompt_lists_scene_and_character():
    """element_refs 应展开为空镜/角色辅助块。"""
    store, refs = _store_with_linked()
    aux = build_linked_assets_aux_prompt(store, {"element_refs": refs})
    assert "【关联资产上下文】" in aux
    assert "空镜「夕阳蜂巢入口」" in aux
    assert "角色「女娲」" in aux
    assert "绯色长袍" in aux or "额间金纹" in aux
    assert "保持上述主体" in aux


def test_merge_prompt_with_linked_assets_appends_once():
    """基础提示词后追加关联块，且不重复。"""
    store, refs = _store_with_linked()
    content = {"element_refs": refs}
    merged = merge_prompt_with_linked_assets("窗边眺望城市", store, content)
    assert merged.startswith("窗边眺望城市")
    assert "【关联资产上下文】" in merged
    again = merge_prompt_with_linked_assets(merged, store, content)
    assert again.count("【关联资产上下文】") == 1


def test_resolve_frame_generation_prompt_appends_when_locked_authored():
    """已锁存 image_prompt 时生图仍拼接关联资产上下文。"""
    store, refs = _store_with_linked()
    content = {
        "image_prompt": "女娲飞入蜂巢",
        "prompt_locked": True,
        "element_refs": refs,
    }
    prompt = resolve_frame_generation_prompt(store, content)
    assert "女娲飞入蜂巢" in prompt
    assert "【关联资产上下文】" in prompt
    assert "夕阳蜂巢入口" in prompt


def test_compose_video_clip_prompt_includes_linked_assets():
    """生视频 compose 应附带关联资产动态上下文。"""
    store, refs = _store_with_linked()
    content = {
        "summary": "飞入",
        "video_prompt": "镜头跟随飞入蜂巢",
        "element_refs": refs,
    }
    prompt = compose_video_clip_prompt(content, store=store)
    assert "镜头跟随飞入蜂巢" in prompt
    assert "【关联资产上下文】" in prompt
    assert "女娲" in prompt
