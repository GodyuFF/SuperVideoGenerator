"""资产详情页二次生成单元测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from core.assets.regenerate import (
    RegenerateError,
    RegenerateNotAllowedError,
    RegenerateNotAvailableError,
    RegenerateNotFoundError,
    assert_regenerate_allowed,
    infer_generation_queue_kind,
    mark_media_superseded,
    mark_text_asset_linked_media_superseded,
    regenerate_asset,
)
from core.llm.agent.script_assets import create_text_asset_for_action
from core.models.entities import (
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    ScriptStatus,
    TextAssetType,
    new_id,
)
from core.store.memory import MemoryStore
from tests.support.image_text_fixtures import character_content, prop_content, scene_content


def _setup_prop_script():
    """创建带道具文字资产的测试剧本。"""
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1", status=ScriptStatus.PLANNED)
    store.add_script(script)
    asset = create_text_asset_for_action(
        store,
        action="create_prop",
        project_id=project.id,
        script_id=script.id,
        asset_name="道具",
        content=prop_content(
            summary="道具",
            description="测试道具描述，用于二次生图验证。",
        ),
        observation="",
    ).asset
    return store, project, script, asset


def test_mark_media_superseded_sets_metadata():
    """mark_media_superseded 应写入 superseded 标记。"""
    store = MemoryStore()
    media = MediaAsset(
        id=new_id("media"),
        project_id="proj_x",
        script_id="scr_x",
        type=MediaAssetType.IMAGE,
        name="img",
        url="/tmp/x.png",
    )
    store.media_assets[media.id] = media
    mark_media_superseded(store, media.id)
    assert media.metadata.get("superseded") is True
    assert media.metadata.get("superseded_at")


def test_mark_text_asset_linked_media_superseded():
    """应按 source 文字资产标记关联图片为 superseded。"""
    store, project, script, asset = _setup_prop_script()
    old_id = new_id("media")
    store.media_assets[old_id] = MediaAsset(
        id=old_id,
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="old",
        url="/tmp/old.png",
        source_asset_id=asset.id,
        metadata={"source_text_asset_id": asset.id},
    )
    mark_text_asset_linked_media_superseded(store, asset.id)
    assert store.media_assets[old_id].metadata.get("superseded") is True


def test_assert_regenerate_allowed_blocks_executing():
    """executing 态剧本应拒绝二次生成。"""
    store, _, script, _ = _setup_prop_script()
    script.status = ScriptStatus.EXECUTING
    with pytest.raises(RegenerateNotAllowedError) as exc:
        assert_regenerate_allowed(store, script)
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "action,content",
    [
        ("create_prop", prop_content(summary="道具", description="测试道具描述，用于二次生图验证。")),
        ("create_character", character_content()),
        ("create_scene", scene_content()),
    ],
)
def test_infer_generation_queue_kind_image_text_types(action, content):
    """character/prop/scene 等图文文字资产应推断为 image 入队。"""
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1", status=ScriptStatus.PLANNED)
    store.add_script(script)
    asset = create_text_asset_for_action(
        store,
        action=action,
        project_id=project.id,
        script_id=script.id,
        asset_name="测试资产",
        content=content,
        observation="",
    ).asset
    assert infer_generation_queue_kind(store, asset.id) == "image"


def test_infer_generation_queue_kind_video_clip():
    """video_clip 文字资产应推断为 video 入队。"""
    from core.models.entities import AssetScope, AssetStatus, TextAsset

    store, project, script, _ = _setup_prop_script()
    clip = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.VIDEO_CLIP,
        name="AI 视频片段",
        content={"video_prompt": "镜头向前推进，城市霓虹闪烁。"},
        scope=AssetScope.SCRIPT_PRIVATE,
        status=AssetStatus.READY,
    )
    store.add_text_asset(clip)
    assert infer_generation_queue_kind(store, clip.id) == "video"


def test_infer_generation_queue_kind_media_image():
    """图片媒体应推断为 image 入队。"""
    store, project, script, _ = _setup_prop_script()
    image_id = new_id("media")
    store.media_assets[image_id] = MediaAsset(
        id=image_id,
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="配图",
        url="/tmp/img.png",
    )
    assert infer_generation_queue_kind(store, image_id) == "image"


def test_infer_generation_queue_kind_media_video():
    """视频媒体应推断为 video 入队。"""
    store, project, script, _ = _setup_prop_script()
    video_id = new_id("media")
    store.media_assets[video_id] = MediaAsset(
        id=video_id,
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.VIDEO,
        name="成片",
        url="/tmp/clip.mp4",
    )
    assert infer_generation_queue_kind(store, video_id) == "video"


def test_infer_generation_queue_kind_media_audio():
    """配音媒体应返回 None，保持同步直跑。"""
    store, project, script, _ = _setup_prop_script()
    audio_id = new_id("media")
    store.media_assets[audio_id] = MediaAsset(
        id=audio_id,
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.AUDIO,
        name="配音",
        url="/tmp/voice.mp3",
        metadata={"shot_id": "shot_x"},
    )
    assert infer_generation_queue_kind(store, audio_id) is None


@pytest.mark.asyncio
async def test_regenerate_asset_not_found():
    """未知资产应返回 404。"""
    store, project, script, _ = _setup_prop_script()
    with pytest.raises(RegenerateNotFoundError):
        await regenerate_asset(
            store,
            None,
            project_id=project.id,
            script_id=script.id,
            asset_id="txt_missing",
        )


@pytest.mark.asyncio
async def test_regenerate_plot_not_supported():
    """plot 文字资产不支持二次生成。"""
    store, project, script, _ = _setup_prop_script()
    from core.models.entities import TextAsset, AssetScope, AssetStatus

    plot = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.PLOT,
        name="剧情",
        content={"text": "hello"},
        scope=AssetScope.SCRIPT_PRIVATE,
        status=AssetStatus.READY,
    )
    store.add_text_asset(plot)
    with pytest.raises(RegenerateError) as exc:
        await regenerate_asset(
            store,
            None,
            project_id=project.id,
            script_id=script.id,
            asset_id=plot.id,
        )
    assert "不支持" in str(exc.value)


@pytest.mark.asyncio
async def test_regenerate_text_asset_without_image_gen():
    """生图未配置时应返回 503。"""
    store, project, script, asset = _setup_prop_script()
    with patch(
        "core.assets.regenerate.is_image_gen_available",
        return_value=False,
    ):
        with pytest.raises(RegenerateNotAvailableError) as exc:
            await regenerate_asset(
                store,
                None,
                project_id=project.id,
                script_id=script.id,
                asset_id=asset.id,
            )
    assert exc.value.status_code == 503


def test_build_regeneration_generation_items_with_existing_image():
    """已有图片的资产二次生成仍应组装出任务项。"""
    from core.llm.tools.image.generate import build_regeneration_generation_items

    store, project, script, asset = _setup_prop_script()
    old_id = new_id("media")
    store.media_assets[old_id] = MediaAsset(
        id=old_id,
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="old",
        url="/tmp/old.png",
        source_asset_id=asset.id,
        metadata={"source_text_asset_id": asset.id},
    )
    asset.primary_media_id = old_id
    store.update_text_asset(asset)

    items = build_regeneration_generation_items(store, script.id, asset.id)
    assert len(items) == 1
    assert items[0]["source_text_asset_id"] == asset.id
    assert str(items[0].get("image_prompt", "")).strip()


@pytest.mark.asyncio
async def test_regenerate_text_asset_success(tmp_path):
    """mock 生图流水线后应成功二次生成。"""
    store, project, script, asset = _setup_prop_script()
    new_media_id = new_id("media")
    png_path = tmp_path / "regen.png"
    png_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    async def fake_run(*_args, **_kwargs):
        from core.llm.agent.llm_action import persist_single_generated_image
        from core.llm.agent.react_core import AgentRunContext

        ctx = AgentRunContext(
            task_brief="",
            work_context={"project_id": project.id, "script_id": script.id},
            script_id=script.id,
            step_id="t",
            agent_name="image_agent",
        )
        item = {
            "source_text_asset_id": asset.id,
            "name": asset.name,
            "image_prompt": "test prompt",
            "url": str(png_path.resolve()),
            "asset_id": new_media_id,
        }
        persist_single_generated_image(store, ctx, item)
        return {"items": [item]}, []

    with patch(
        "core.assets.regenerate.is_image_gen_available",
        return_value=True,
    ), patch(
        "core.assets.regenerate.run_concurrent_image_generation",
        new=AsyncMock(side_effect=fake_run),
    ):
        result = await regenerate_asset(
            store,
            None,
            project_id=project.id,
            script_id=script.id,
            asset_id=asset.id,
        )

    assert result.ok is True
    assert result.kind == "image"
    assert new_media_id in store.media_assets
