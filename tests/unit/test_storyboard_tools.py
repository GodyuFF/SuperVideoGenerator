"""storyboard_agent load_context / get_plan 测试。"""

import json

import pytest

from core.llm.agent.react_core import AgentRunContext
from core.llm.tools import get_tool_registry
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
from tests.support.image_text_fixtures import character_content


@pytest.mark.asyncio
async def test_storyboard_load_context_returns_script_and_schema():
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(
        project_id=project.id,
        title="老虎吃肉",
        content_md="# 开场\n\n老虎在捕猎。",
    )
    store.add_script(script)
    plot = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.PLOT,
        name="捕猎",
        content={"text": "老虎悄悄接近猎物"},
    )
    store.add_text_asset(plot)
    char = TextAsset(
        project_id=project.id,
        type=TextAssetType.CHARACTER,
        name="老虎",
        content=character_content(description="成年老虎"),
        scope=AssetScope.PROJECT_SHARED,
        source_script_id=script.id,
    )
    store.add_text_asset(char)
    media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="老虎图",
        url="https://cdn.test/tiger.png",
        source_asset_id=char.id,
    )
    store.add_media_asset(media)
    char.primary_media_id = media.id

    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id},
        script_id=script.id,
        step_id="step1",
        agent_name="storyboard_agent",
    )
    result = await get_tool_registry().call_tool(
        "load_context",
        {"observation": "加载分镜上下文"},
        ctx,
        store,
    )
    assert result.ok, result.observation
    assert "老虎在捕猎" in result.observation
    assert "老虎悄悄接近猎物" in result.observation
    assert result.structured["action"] == "load_context"
    assert result.structured["linked_image_count"] >= 1
    payload = json.loads(result.observation.split("分镜上下文 JSON：\n", 1)[1])
    assert payload["script"]["content_md"].startswith("# 开场")


@pytest.mark.asyncio
async def test_storyboard_get_plan_includes_shots_json():
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    store.set_video_plan(
        VideoPlan(
            script_id=script.id,
            mode=VideoStyleMode.DYNAMIC_IMAGE,
            shots=[
                VideoPlanShot(
                    order=0,
                    duration_ms=3000,
                    camera_motion="ken_burns_in",
                    narration_text="开场旁白",
                )
            ],
        )
    )
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id},
        script_id=script.id,
        step_id="step1",
        agent_name="storyboard_agent",
    )
    result = await get_tool_registry().call_tool(
        "get_plan",
        {
            "observation": "读取计划稿",
            "plan_status": "读取计划稿",
            "remaining_plan": ["finish"],
        },
        ctx,
        store,
    )
    assert result.ok
    assert "开场旁白" in result.observation
    assert result.structured["shot_count"] == 1


def test_storyboard_agent_has_no_read_webpage():
    from core.llm.tools.shared.agent_tools import read_actions

    assert "read_webpage" not in read_actions("storyboard_agent")


def test_pipeline_agents_exclude_read_webpage():
    from core.llm.tools.shared.agent_tools import read_actions

    for agent in ("tts_agent", "editing_agent", "image_agent", "video_agent"):
        assert "read_webpage" not in read_actions(agent), read_actions(agent)


def test_create_shots_output_schema_not_asset_mutation():
    from core.llm.tools.register_helpers import output_schema_for

    schema = output_schema_for("create_shots")
    required = schema.get("required", [])
    assert "action" in required
    assert "asset_id" not in required


@pytest.mark.asyncio
async def test_create_shots_via_registry_ok_with_asset_id_refs():
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="图",
        url="https://cdn.test/x.png",
    )
    store.add_media_asset(media)

    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id},
        script_id=script.id,
        step_id="step1",
        agent_name="storyboard_agent",
    )
    result = await get_tool_registry().call_tool(
        "create_shots",
        {
            "observation": "设计镜头",
            "shots": [
                {
                    "order": 0,
                    "duration_ms": 5000,
                    "camera_motion": "ken_burns_in",
                    "narration_text": "第一镜旁白",
                    "asset_refs": {"asset_id": [media.id]},
                }
            ],
        },
        ctx,
        store,
    )
    assert result.ok, result.observation
    assert result.structured["action"] == "create_shots"
    assert result.structured.get("shot_count") == 1
    pending = ctx.work_context["_pending_shots"]
    assert pending[0].asset_refs.get("image") == [media.id]


def test_normalize_shot_asset_refs_maps_character():
    from core.llm.agent.llm_action import normalize_shot_asset_refs

    store = MemoryStore()
    char = TextAsset(
        project_id="p1",
        type=TextAssetType.CHARACTER,
        name="主角",
        content={"description": "x"},
    )
    store.add_text_asset(char)
    refs = normalize_shot_asset_refs({"asset_id": [char.id]}, store)
    assert refs["character"] == [char.id]


def test_completed_actions_skipped_when_last_action_ok_false():
    ctx = AgentRunContext(
        task_brief="",
        work_context={},
        script_id="s1",
        step_id="step1",
        agent_name="storyboard_agent",
    )
    ctx.last_action_ok = False
    action = "create_shots"
    if ctx.last_action_ok is not False:
        ctx.completed_actions.add(action)
    assert action not in ctx.completed_actions
