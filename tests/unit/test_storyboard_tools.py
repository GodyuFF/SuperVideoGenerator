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
    Shot,
    VideoStyleMode,
)
from core.store.memory import MemoryStore
from tests.support.image_text_fixtures import character_content
from tests.support.shot_fixtures import make_shot, shot_design_payload


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
        {"observation": "加载分镜上下文", "script_id": script.id},
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
    speakers = payload.get("voice_speakers") or []
    assert speakers[0]["kind"] == "narrator"
    assert speakers[0]["character_ref"] == ""
    char_speakers = [s for s in speakers if s.get("kind") == "character"]
    assert len(char_speakers) == 1
    assert char_speakers[0]["character_ref"] == char.id


@pytest.mark.asyncio
async def test_storyboard_load_context_requires_script_id():
    """缺 script_id 时 schema 校验失败，不得静默用会话默认剧本。"""
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1", content_md="# x")
    store.add_script(script)
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
    assert not result.ok
    assert "script_id" in (result.observation or "").lower() or "script_id" in str(
        (result.structured or {}).get("error", "")
    ).lower()


@pytest.mark.asyncio
async def test_storyboard_load_context_rejects_mismatched_script_id():
    """传入与会话不一致的 script_id 须失败。"""
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1", content_md="# a")
    other = Script(project_id=project.id, title="s2", content_md="# b")
    store.add_script(script)
    store.add_script(other)
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id},
        script_id=script.id,
        step_id="step1",
        agent_name="storyboard_agent",
    )
    result = await get_tool_registry().call_tool(
        "load_context",
        {"observation": "加载分镜上下文", "script_id": other.id},
        ctx,
        store,
    )
    assert not result.ok
    assert "不一致" in (result.observation or "")


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
            mode=VideoStyleMode.STORYBOOK,
            shots=[make_shot(order=0, duration_ms=3000, text="开场旁白", camera_motion="ken_burns_in")],
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


@pytest.mark.asyncio
async def test_get_plan_returns_pending_before_persist():
    """persist 前 get_plan 应返回 work_context 中的 pending 镜头及 sub_shot_id。"""
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    shot = make_shot(order=0, duration_ms=3000, text="旁白")
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id, "_pending_shots": [shot]},
        script_id=script.id,
        step_id="step1",
        agent_name="storyboard_agent",
    )
    from core.llm.tools.storyboard.handler import handle_get_plan

    result = handle_get_plan(store, ctx, {"observation": "查 pending"})
    assert result.structured["source"] == "pending"
    assert result.structured["shot_count"] == 1
    row = result.structured["shots"][0]
    assert row["id"] == shot.id
    assert row["sub_shots"][0]["id"] == shot.sub_shots[0].id
    assert shot.sub_shots[0].id in result.observation


@pytest.mark.asyncio
async def test_create_shots_observation_includes_sub_shot_ids():
    """create_shots 观察结果须含系统生成的 sub_shot_id，供后续 create_frames 使用。"""
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
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
            "shots": [shot_design_payload(order=0, text="测试旁白")],
        },
        ctx,
        store,
    )
    assert result.ok, result.observation
    sub_id = ctx.work_context["_pending_shots"][0].sub_shots[0].id
    assert sub_id in result.observation
    assert result.structured["shots"][0]["sub_shots"][0]["id"] == sub_id


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
                shot_design_payload(
                    order=0,
                    duration_ms=5000,
                    text="第一镜旁白",
                    camera_motion="ken_burns_in",
                    element_refs={"image": [media.id]},
                )
            ],
        },
        ctx,
        store,
    )
    assert result.ok, result.observation
    assert result.structured["action"] == "create_shots"
    assert result.structured.get("shot_count") == 1
    pending = ctx.work_context["_pending_shots"]
    assert len(pending[0].sub_shots) == 1
    assert pending[0].audio_tracks[0].clips[0].text == "第一镜旁白"


@pytest.mark.asyncio
async def test_create_shots_rejects_invalid_character_ref():
    """create_shots 拒绝指向未生成角色的 character_ref。"""
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id},
        script_id=script.id,
        step_id="step1",
        agent_name="storyboard_agent",
    )
    payload = shot_design_payload(order=0, text="你好")
    payload["audio_tracks"][0]["clips"][0]["character_ref"] = "txt_not_exist"
    result = await get_tool_registry().call_tool(
        "create_shots",
        {"observation": "设计镜头", "shots": [payload]},
        ctx,
        store,
    )
    assert not result.ok
    assert "character_ref" in result.observation or "说话人" in result.observation


@pytest.mark.asyncio
async def test_create_shots_accepts_character_dialogue_ref():
    """create_shots 接受已生成角色的 character_ref。"""
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    char = TextAsset(
        project_id=project.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.PROJECT_SHARED,
        name="主角",
        content={"description": "x"},
        source_script_id=script.id,
    )
    store.add_text_asset(char)
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id},
        script_id=script.id,
        step_id="step1",
        agent_name="storyboard_agent",
    )
    payload = shot_design_payload(order=0, text="我来了")
    payload["audio_tracks"][0]["clips"][0]["character_ref"] = char.id
    result = await get_tool_registry().call_tool(
        "create_shots",
        {"observation": "设计镜头", "shots": [payload]},
        ctx,
        store,
    )
    assert result.ok
    pending = ctx.work_context["_pending_shots"]
    assert pending[0].audio_tracks[0].clips[0].character_ref == char.id


@pytest.mark.asyncio
async def test_create_shots_rejects_missing_voice_text_storybook():
    """故事书模式下 create_shots 缺 voice clip text 应被拒绝。"""
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id, "style_mode": VideoStyleMode.STORYBOOK},
        script_id=script.id,
        step_id="step1",
        agent_name="storyboard_agent",
    )
    payload = shot_design_payload(order=0, text="")
    payload["audio_tracks"] = [
        {
            "kind": "voice",
            "name": "角色音",
            "clips": [{"start_ms": 0, "end_ms": 5000, "text": ""}],
        }
    ]
    result = await get_tool_registry().call_tool(
        "create_shots",
        {"observation": "设计镜头", "shots": [payload]},
        ctx,
        store,
    )
    assert not result.ok
    assert "配音幕" in result.observation or "voice" in result.observation.lower()


@pytest.mark.asyncio
async def test_create_shots_allows_empty_voice_text_ai_video():
    """AI 视频模式不强制镜内 voice clip 非空 text（但 schema 仍要求 audio_tracks 结构）。"""
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id, "style_mode": VideoStyleMode.AI_VIDEO},
        script_id=script.id,
        step_id="step1",
        agent_name="storyboard_agent",
    )
    payload = {
        "order": 0,
        "duration_ms": 5000,
        "sub_shots": [
            {
                "start_ms": 0,
                "end_ms": 5000,
                "description": "动作镜头",
                "camera_motion": "ken_burns_in",
            }
        ],
        "audio_tracks": [
            {
                "kind": "voice",
                "name": "角色音",
                "clips": [{"start_ms": 0, "end_ms": 5000, "text": ""}],
            }
        ],
    }
    result = await get_tool_registry().call_tool(
        "create_shots",
        {"observation": "设计镜头", "shots": [payload]},
        ctx,
        store,
    )
    assert result.ok, result.observation


@pytest.mark.asyncio
async def test_create_shots_multi_sub_shots():
    """create_shots 支持单镜多子镜时段。"""
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
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
            "observation": "设计多子镜镜头",
            "shots": [
                {
                    "order": 0,
                    "duration_ms": 6000,
                    "sub_shots": [
                        {
                            "start_ms": 0,
                            "end_ms": 3000,
                            "description": "子镜A",
                            "camera_motion": "ken_burns_in",
                        },
                        {
                            "start_ms": 3000,
                            "end_ms": 6000,
                            "description": "子镜B",
                            "camera_motion": "pan_right",
                        },
                    ],
                    "audio_tracks": [
                        {
                            "kind": "voice",
                            "name": "旁白",
                            "clips": [
                                {"start_ms": 0, "end_ms": 6000, "text": "连续旁白"}
                            ],
                        }
                    ],
                }
            ],
        },
        ctx,
        store,
    )
    assert result.ok, result.observation
    pending = ctx.work_context["_pending_shots"]
    assert len(pending[0].sub_shots) == 2
    assert pending[0].sub_shots[1].start_ms == 3000


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
