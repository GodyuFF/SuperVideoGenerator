"""image search / sync 工具测试。"""

from core.edit.image_sync import split_image_observations
from core.llm.agent.react_core import AgentRunContext
from core.llm.agent.script_assets import create_text_asset_for_action
from core.llm.tools.image.search_sync import handle_sync_text_from_image
from core.llm.tools.output_schemas import sync_text_from_image_output_schema
from core.llm.tools.validators import validate_against_schema
from core.models.entities import MediaAsset, MediaAssetType, Project, Script
from core.store.memory import MemoryStore
from tests.support.image_text_fixtures import prop_content


def test_sync_text_from_image_auto_patch():
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    asset = create_text_asset_for_action(
        store,
        action="create_prop",
        project_id=project.id,
        script_id=script.id,
        asset_name="道具",
        content=prop_content(summary="道具", description="旧描述"),
        observation="",
    )
    media = MediaAsset(
        id="media_search_patch",
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="search",
        url="projects/x/scripts/y/assets/media/media_search_patch.png",
        metadata={"source": "search"},
    )
    store.add_media_asset(media)
    asset.primary_media_id = media.id
    store.update_text_asset(asset)
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id, "script_id": script.id},
        script_id=script.id,
        step_id="step_1",
        agent_name="image_agent",
    )
    result = handle_sync_text_from_image(
        store,
        ctx,
        {
            "observation": "同步搜图观察",
            "asset_id": asset.id,
            "image_observations": {
                "color_palette": "暖色",
                "visual_style": "纪实",
                "description": "新描述应待确认",
            },
        },
    )
    assert result.ok
    validate_against_schema(
        result.structured, sync_text_from_image_output_schema(), label="输出"
    )
    updated = store.get_text_asset(asset.id)
    assert updated
    assert updated.content.get("color_palette") == "暖色"
    assert updated.content.get("description") == "旧描述"
    auto, major, _ = split_image_observations({"description": "新描述应待确认"})
    assert "description" in major


def test_sync_skipped_for_generated_image():
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    asset = create_text_asset_for_action(
        store,
        action="create_prop",
        project_id=project.id,
        script_id=script.id,
        asset_name="道具",
        content=prop_content(summary="道具", description="描述"),
        observation="",
    )
    media = MediaAsset(
        id="media_gen",
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="gen",
        url="projects/x/scripts/y/assets/media/media_gen.png",
        metadata={"source": "agnes"},
    )
    store.add_media_asset(media)
    asset.primary_media_id = media.id
    store.update_text_asset(asset)
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id, "script_id": script.id},
        script_id=script.id,
        step_id="step_1",
        agent_name="image_agent",
    )
    result = handle_sync_text_from_image(
        store,
        ctx,
        {
            "observation": "不应执行",
            "asset_id": asset.id,
            "image_observations": {"color_palette": "暖色"},
        },
    )
    assert result.ok
    assert result.structured["skipped"] is True
    updated = store.get_text_asset(asset.id)
    assert updated
    assert updated.content.get("color_palette") != "暖色"


def test_scan_sync_pending_false_for_generated_image():
    from core.llm.tools.image.scan import build_scan_text_assets_payload

    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    asset = create_text_asset_for_action(
        store,
        action="create_prop",
        project_id=project.id,
        script_id=script.id,
        asset_name="道具",
        content=prop_content(summary="道具", description="测试道具描述足够长用于通过校验。"),
        observation="",
    )
    media = MediaAsset(
        id="media_gen2",
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="gen",
        url="projects/x/scripts/y/assets/media/media_gen2.png",
        metadata={"source": "agnes"},
    )
    store.add_media_asset(media)
    asset.primary_media_id = media.id
    store.update_text_asset(asset)
    payload = build_scan_text_assets_payload(store, script.id)
    row = next(a for a in payload["assets"] if a["id"] == asset.id)
    assert row["sync_pending"] is False


def test_scan_sync_pending_true_for_search_image():
    from core.llm.tools.image.scan import build_scan_text_assets_payload

    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    asset = create_text_asset_for_action(
        store,
        action="create_prop",
        project_id=project.id,
        script_id=script.id,
        asset_name="道具",
        content=prop_content(summary="道具", description="测试道具描述足够长用于通过校验。"),
        observation="",
    )
    media = MediaAsset(
        id="media_search",
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="search",
        url="projects/x/scripts/y/assets/media/media_search.png",
        metadata={"source": "search"},
    )
    store.add_media_asset(media)
    asset.primary_media_id = media.id
    store.update_text_asset(asset)
    payload = build_scan_text_assets_payload(store, script.id)
    row = next(a for a in payload["assets"] if a["id"] == asset.id)
    assert row["sync_pending"] is True


def test_scan_includes_source_mode_and_sync_pending():
    from core.llm.tools.image.scan import build_scan_text_assets_payload

    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    create_text_asset_for_action(
        store,
        action="create_prop",
        project_id=project.id,
        script_id=script.id,
        asset_name="道具",
        content=prop_content(summary="道具", description="测试道具描述足够长用于通过校验。"),
        observation="",
    )
    payload = build_scan_text_assets_payload(store, script.id)
    assert "source_mode" in payload
    assert payload["assets"][0].get("sync_pending") is False
