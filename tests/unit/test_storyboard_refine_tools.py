"""storyboard_refine_agent tools 测试。"""

import pytest

from core.conversation import ConversationStore
from core.events.emitter import EventEmitter
from core.llm.agent.llm_agents import StoryboardRefineAgent
from core.llm.tools.shared.agent_tools import available_actions
from core.llm.agent.react_core import AgentRunContext
from core.llm.client import LLMClient
from core.llm.client.settings import LLMConfigManager
from core.llm.tools.register_helpers import output_schema_for
from core.llm.tools.registry import get_tool_registry, reset_tool_registry
from core.llm.tools.storyboard_refine.handler import (
    handle_get_plan,
    handle_get_shot_asset_timing,
    handle_get_shot_details,
    handle_review_and_restructure,
    handle_review_shot,
    handle_sync_actual_assets,
)
from core.llm.tools.storyboard_refine.schemas import STORYBOARD_REFINE_SCHEMAS
from core.models.entities import (
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    VideoPlan,
    Shot,
    VideoStyleMode,
)
from core.store.memory import MemoryStore
from tests.support.frame_fixtures import ensure_shot_frame_image
from tests.support.shot_fixtures import make_shot

_AGENT = "storyboard_refine_agent"
_PLAN_TRACKING = {
    "plan_status": "测试中",
    "remaining_plan": ["finish"],
}
_CANONICAL_REFINE_TOOLS = frozenset(
    {
        "get_shot_details",
        "get_shot_asset_timing",
        "get_refine_plan",
        "sync_actual_assets",
        "analyze_av_sync",
        "review_shot",
        "review_and_restructure",
        "update_frames",
        "persist_review",
    }
)
_LEGACY_REFINE_ACTIONS = frozenset(
    {
        "load_review_context",
        "load_refine_context",
        "sync_from_tts",
        "refine_shots",
        "persist_shot_detail",
    }
)


def _ctx(store: MemoryStore, script_id: str) -> AgentRunContext:
    return AgentRunContext(
        script_id=script_id,
        conversation_id="conv_test",
        step_id="step_test",
        task_brief="test",
        agent_name=_AGENT,
        work_context={},
        outputs=[],
    )


def _refine_fixture(
    store: MemoryStore,
    *,
    with_tts: bool = False,
    with_shot_detail: bool = False,
) -> tuple[Project, Script, Shot, AgentRunContext]:
    """构建含 VideoPlan、frame 图与可选 TTS/shot_detail 的最小复核场景。"""
    project = Project(title="refine tools")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1", duration_sec=30)
    store.add_script(script)
    shot = make_shot(order=0, duration_ms=3000, text="旁白")
    if with_shot_detail:
        shot = shot.model_copy(update={"review_note": "画面焦点在主体"})
    ensure_shot_frame_image(
        store,
        project_id=project.id,
        script_id=script.id,
        shot=shot,
        image_url="https://images.test/frame.png",
    )
    store.set_video_plan(
        VideoPlan(script_id=script.id, mode=VideoStyleMode.STORYBOOK, shots=[shot])
    )
    if with_tts:
        audio = MediaAsset(
            project_id=project.id,
            script_id=script.id,
            type=MediaAssetType.AUDIO,
            name="tts",
            url="https://audio.test/a.mp3",
            metadata={
                "shot_id": shot.id,
                "duration_ms": 4500,
                "subtitle_cues": [{"text": "旁白", "start_ms": 0, "end_ms": 4500}],
            },
        )
        store.add_media_asset(audio)
        from core.edit.shot_detail_sync import sync_plan_from_tts

        sync_plan_from_tts(store, script.id)
        plan = store.get_video_plan_for_script(script.id)
        assert plan
        shot = plan.shots[0]
    return project, script, shot, _ctx(store, script.id)


def test_get_shot_details_sub_shot_level_gaps():
    """get_shot_details 返回子镜级缺图 image_gap_sub_shots。"""
    from core.models.entities import ShotSubShot, new_id

    store = MemoryStore()
    project = Project(title="gap")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    shot = make_shot(order=0, duration_ms=6000, text="旁白")
    sub_b = ShotSubShot(
        id=new_id("ssb"),
        start_ms=3000,
        end_ms=6000,
        description="第二子镜",
        camera_motion="static",
    )
    shot = shot.model_copy(update={"sub_shots": [shot.sub_shots[0], sub_b]})
    ensure_shot_frame_image(
        store,
        project_id=project.id,
        script_id=script.id,
        shot=shot,
        image_url="https://images.test/frame.png",
    )
    store.set_video_plan(
        VideoPlan(script_id=script.id, mode=VideoStyleMode.STORYBOOK, shots=[shot])
    )
    ctx = _ctx(store, script.id)
    result = handle_get_shot_details(store, ctx, {"observation": "查详情", **_PLAN_TRACKING})
    assert result.ok is not False
    gaps = result.structured.get("image_gap_sub_shots") or []
    assert gaps
    assert any(g["sub_shot_id"] == sub_b.id and g["missing_frame"] for g in gaps)
    assert shot.id in result.structured.get("image_gap_shot_ids", [])


def test_get_shot_details_excludes_text_segments():
    """get_shot_details 返回 plan/detail，不含 text_segments。"""
    store = MemoryStore()
    _, _, shot, ctx = _refine_fixture(store, with_tts=True, with_shot_detail=True)
    result = handle_get_shot_details(
        store, ctx, {"observation": "查详情", **_PLAN_TRACKING}
    )
    assert result.ok is not False
    assert result.structured["shot_count"] == 1
    row = result.structured["shots"][0]
    assert row["id"] == shot.id
    assert "sub_shots" in row or row.get("review_note")
    assert "text_segments" not in row
    dumped = str(result.structured)
    assert "text_segments" not in dumped or "text_segments" not in row


def test_get_shot_asset_timing_audio_text_segments():
    """get_shot_asset_timing 在 with_tts 时返回非空 text_segments。"""
    store = MemoryStore()
    _, _, shot, ctx = _refine_fixture(store, with_tts=True)
    result = handle_get_shot_asset_timing(
        store,
        ctx,
        {"observation": "查时长", **_PLAN_TRACKING, "asset_kind": "audio"},
    )
    assert result.ok is not False
    row = result.structured["shots"][0]
    assert row["shot_id"] == shot.id
    audio = row["assets"]["audio"]
    assert audio["duration_ms"] == row["actual_duration_ms"]
    assert audio["duration_ms"] == 4500
    assert "duration_source" in audio
    assert "metadata_duration_ms" in audio
    segments = audio.get("text_segments") or []
    assert segments
    assert segments[0]["text"]
    assert "video" not in row["assets"]


def test_storyboard_refine_query_and_sync():
    """查询分镜详情与同步实测资产可串联执行。"""
    store = MemoryStore()
    _, script, shot, ctx = _refine_fixture(store, with_tts=True)

    details_result = handle_get_shot_details(store, ctx, {"observation": "查详情", **_PLAN_TRACKING})
    assert details_result.ok is not False
    assert details_result.structured["shot_count"] == 1

    sync_result = handle_sync_actual_assets(store, ctx, {"observation": "同步"})
    assert sync_result.ok is not False
    assert sync_result.structured["shot_count"] == 1

    plan_result = handle_get_plan(store, ctx, {})
    assert plan_result.structured["shot_count"] == 1
    assert plan_result.structured["shots"][0]["duration_ms"] == 4500


def test_all_refine_tools_input_schema_has_plan_tracking():
    """全部 refine tool 输入 schema 均含 plan_status / remaining_plan。"""
    assert set(STORYBOARD_REFINE_SCHEMAS.keys()) == _CANONICAL_REFINE_TOOLS
    for name, schema in STORYBOARD_REFINE_SCHEMAS.items():
        props = schema.get("properties") or {}
        assert "plan_status" in props, f"{name} 缺少 plan_status"
        assert "remaining_plan" in props, f"{name} 缺少 remaining_plan"
        if name == "get_refine_plan":
            required = schema.get("required") or []
            assert "plan_status" in required, name
            assert "remaining_plan" in required, name


def test_review_and_restructure_preflight_invalid_shot_id():
    """无效 shot_id 须 preflight 失败且 store 未变更。"""
    store = MemoryStore()
    _, script, shot, ctx = _refine_fixture(store)
    vp_before = store.get_video_plan_for_script(script.id)
    assert vp_before is not None
    rev_before = vp_before.detail_revision

    result = handle_review_and_restructure(
        store,
        ctx,
        {
            "observation": "无效 op",
            **_PLAN_TRACKING,
            "restructure_ops": [{"op": "adjust", "shot_id": "shot_nonexistent"}],
        },
    )
    assert result.ok is False
    assert result.structured.get("valid") is False
    assert "shot_nonexistent" in result.structured.get("error", "")

    vp_after = store.get_video_plan_for_script(script.id)
    assert vp_after is not None
    assert vp_after.detail_revision == rev_before
    assert vp_after.shots[0].id == shot.id


def test_review_shot_patch_only():
    """review_shot 仅 patch 时应写入 review_note。"""
    store = MemoryStore()
    _, script, shot, ctx = _refine_fixture(store, with_shot_detail=True)
    result = handle_review_shot(
        store,
        ctx,
        {
            "observation": "单镜展示说明",
            **_PLAN_TRACKING,
            "shot_id": shot.id,
            "patch": {
                "display_instructions": "0~3s 全景无字幕，3.5s 字幕出现",
                "camera_motion_refined": "ken_burns_in",
            },
        },
    )
    assert result.ok is True
    assert result.structured.get("action") == "review_shot"
    assert result.structured.get("shot_id") == shot.id
    vp = store.get_video_plan_for_script(script.id)
    assert vp is not None
    assert "全景无字幕" in (vp.shots[0].review_note or "")


def test_review_shot_rejects_cross_shot_merge():
    """review_shot 不允许 merge 等跨镜 op。"""
    store = MemoryStore()
    _, script, shot, ctx = _refine_fixture(store)
    result = handle_review_shot(
        store,
        ctx,
        {
            "observation": "非法跨镜",
            **_PLAN_TRACKING,
            "shot_id": shot.id,
            "restructure_op": {"op": "merge", "shot_ids": [shot.id, "shot_x"]},
        },
    )
    assert result.ok is False
    assert "review_and_restructure" in result.structured.get("error", "")


def test_storyboard_refine_output_schemas_no_generic_shadowing():
    """update_frames 不得被 startswith update_ 误匹配为资产变更 schema。"""
    schema = output_schema_for("update_frames")
    required = schema.get("required", [])
    assert "updated_frame_count" in required
    assert "asset_id" not in required
    assert "action" not in required

    plan_schema = output_schema_for("get_refine_plan")
    assert "action" not in plan_schema.get("required", [])
    assert "detail_revision" in plan_schema.get("properties", {})


def test_legacy_refine_actions_not_registered():
    """已删除的兼容别名不得出现在 Registry 与 Agent available_actions。"""
    reset_tool_registry()
    registry = get_tool_registry()
    refine_registered = {
        spec.name for spec in registry.list_tools(agent=_AGENT)
    }
    assert refine_registered == _CANONICAL_REFINE_TOOLS
    assert refine_registered & _LEGACY_REFINE_ACTIONS == set()

    available = set(available_actions(_AGENT))
    assert available & _LEGACY_REFINE_ACTIONS == set()
    assert _CANONICAL_REFINE_TOOLS.issubset(available)

    for legacy in _LEGACY_REFINE_ACTIONS:
        assert registry.get(legacy) is None


@pytest.mark.asyncio
async def test_legacy_load_review_context_alias_executes_get_shot_details():
    """废弃 load_review_context 须在运行时重定向到 get_shot_details，避免 generic action schema 报错。"""
    reset_tool_registry()
    store = MemoryStore()
    _, script, _, ctx = _refine_fixture(store, with_tts=True, with_shot_detail=True)
    agent = StoryboardRefineAgent(
        store,
        EventEmitter(),
        ConversationStore(),
        LLMConfigManager(),
        LLMClient(LLMConfigManager()),
    )
    run_ctx = AgentRunContext(
        script_id=script.id,
        conversation_id="conv_legacy_alias",
        step_id="step_legacy",
        task_brief="test",
        agent_name=_AGENT,
        work_context={},
        outputs=[],
        current_action_input={
            "observation": "加载复核上下文",
            **_PLAN_TRACKING,
        },
    )
    obs = await agent.execute_action("load_review_context", run_ctx)
    assert run_ctx.last_action_ok is not False
    assert "action' is a required property" not in obs
    assert "shot_count" in obs


@pytest.mark.asyncio
async def test_legacy_refine_call_tool_unknown():
    """调用已删除 action 时 Registry 返回未知 tool。"""
    reset_tool_registry()
    store = MemoryStore()
    _, script, _, ctx = _refine_fixture(store)
    registry = get_tool_registry()
    result = await registry.call_tool(
        "load_review_context",
        {"observation": "legacy", **_PLAN_TRACKING},
        ctx,
        store,
    )
    assert result.ok is False
    assert "未知" in result.observation

@pytest.mark.asyncio
async def test_agent_picks_up_refreshed_tool_registry():
    """reset_tool_registry 后子 Agent 须使用新 output_schema，而非 init 时缓存的旧 Registry。"""
    reset_tool_registry()
    store = MemoryStore()
    _, script, _, _ = _refine_fixture(store)
    llm_config = LLMConfigManager()
    agent = StoryboardRefineAgent(
        store,
        EventEmitter(),
        ConversationStore(),
        llm_config,
        LLMClient(llm_config),
    )
    run_ctx = AgentRunContext(
        script_id=script.id,
        conversation_id="conv_refresh",
        step_id="step_refresh",
        task_brief="test",
        agent_name=_AGENT,
        work_context={},
        outputs=[],
        current_action_input={
            "observation": "查询分镜详情",
            **_PLAN_TRACKING,
        },
    )
    obs = await agent.execute_action("get_shot_details", run_ctx)
    assert run_ctx.last_action_ok is not False
    assert "action' is a required property" not in obs
    assert "shot_count" in obs


@pytest.mark.asyncio
async def test_get_shot_details_registry_output_schema():
    """get_shot_details 结构化输出须通过 Registry output_schema 校验。"""
    reset_tool_registry()
    store = MemoryStore()
    _, script, _, ctx = _refine_fixture(store)
    result = await get_tool_registry().call_tool(
        "get_shot_details",
        {"observation": "查询分镜详情", **_PLAN_TRACKING},
        ctx,
        store,
    )
    assert result.ok, result.observation
    assert result.structured["shot_count"] == 1
    assert "action" not in result.structured


@pytest.mark.asyncio
async def test_get_refine_plan_registry_output_schema():
    """get_refine_plan 输出不含 action，须通过 refine_plan_output_schema。"""
    reset_tool_registry()
    store = MemoryStore()
    _, _, _, ctx = _refine_fixture(store)
    result = await get_tool_registry().call_tool(
        "get_refine_plan",
        {"observation": "读取计划", **_PLAN_TRACKING},
        ctx,
        store,
    )
    assert result.ok, result.observation
    assert result.structured["shot_count"] == 1
    assert "action" not in result.structured
    assert "detail_revision" in result.structured


@pytest.mark.asyncio
async def test_update_frames_registry_output_schema():
    """update_frames 输出须为 updated_frame_count，非 asset_mutation。"""
    reset_tool_registry()
    store = MemoryStore()
    _, _, _, ctx = _refine_fixture(store, with_shot_detail=True)
    result = await get_tool_registry().call_tool(
        "update_frames",
        {"observation": "更新 frame", **_PLAN_TRACKING},
        ctx,
        store,
    )
    assert result.ok, result.observation
    assert result.structured["updated_frame_count"] >= 0
    assert "action" not in result.structured


@pytest.mark.asyncio
async def test_all_storyboard_refine_output_schemas_match_handlers():
    """分镜复核 Agent 全部注册 tool 的 structured 输出须通过 output_schema。"""
    reset_tool_registry()
    store = MemoryStore()
    _, script, shot, ctx = _refine_fixture(store, with_tts=True, with_shot_detail=True)
    registry = get_tool_registry()
    tracking = dict(_PLAN_TRACKING)
    patch = {
        "shot_id": shot.id,
        "display_instructions": "字幕区在下方，主体居中",
    }
    tool_args: dict[str, dict] = {
        "get_shot_details": {"observation": "查详情", **tracking},
        "get_shot_asset_timing": {
            "observation": "查时长",
            **tracking,
            "asset_kind": "all",
        },
        "sync_actual_assets": {"observation": "同步实测", **tracking},
        "get_refine_plan": {"observation": "读计划", **tracking},
        "update_frames": {"observation": "更新 frame", **tracking},
        "review_shot": {
            "observation": "单镜复核",
            **tracking,
            "shot_id": shot.id,
            "patch": patch,
        },
        "review_and_restructure": {
            "observation": "复核",
            **tracking,
            "restructure_ops": [{"op": "adjust", "shot_id": shot.id, **patch}],
        },
        "persist_review": {"observation": "保存复核", **tracking},
    }
    mutation_fields = {
        "action",
        "detail_revision",
        "shot_count",
        "restructure_op_count",
        "patched_shot_count",
    }
    persist_fields = {"action", "plan_id", "detail_revision"}

    for name, args in tool_args.items():
        result = await registry.call_tool(name, args, ctx, store)
        assert result.ok, f"{name}: {result.observation}"
        if name in ("review_and_restructure", "review_shot"):
            assert mutation_fields.issubset(result.structured.keys()), name
        if name == "persist_review":
            assert persist_fields.issubset(result.structured.keys()), name
        if name == "sync_actual_assets":
            assert "plan_id" in result.structured, name
            assert "detail_revision" in result.structured, name


@pytest.mark.asyncio
async def test_refine_output_schema_registry_matches_helpers():
    """refine 域 tool 注册 output_schema 须与 output_schema_for 一致。"""
    reset_tool_registry()
    registry = get_tool_registry()
    refine_names = set(STORYBOARD_REFINE_SCHEMAS.keys())
    drift: list[str] = []
    for spec in registry.list_tools():
        if spec.name not in refine_names:
            continue
        expected = output_schema_for(spec.name)
        if spec.output_schema != expected:
            drift.append(
                f"{spec.name}: registered required={spec.output_schema.get('required')} "
                f"expected required={expected.get('required')}"
            )
    assert not drift, "refine output_schema 漂移:\n" + "\n".join(drift)
