"""全 Registry tool 的 output_schema 与 handler structured 对齐测试。"""

from __future__ import annotations

import jsonschema
import pytest

from core.edit.export_jobs import create_export_job
from core.edit.timeline import compile_timeline_from_shots
from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.register_helpers import output_schema_for
from core.llm.tools.registry import get_tool_registry, reset_tool_registry
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
from tests.support.frame_fixtures import ensure_shot_frame_image
from tests.support.image_text_fixtures import prop_content

_PLAN_TRACKING = {
    "plan_status": "schema 测试",
    "remaining_plan": ["finish"],
}

# 需网络、后台任务、专用异常路径或复杂写参，跳过 call_tool 矩阵
_SKIP_CALL_MATRIX = frozenset(
    {
        "web_search",
        "read_webpage",
        "export_timeline",
        "report_missing_assets",
        "return_to_master",
        "compose_final",
        "generate_clips",
        "generate_video_clips",
        "generate_images",
        "generate_from_timeline",
        "synthesize",
        "extract_narration",
        "search_images",
        "sync_text_from_image",
        # 写 pipeline / ad_hoc 需完整 LLM 参数，由域内单测覆盖
        "create_character",
        "create_prop",
        "create_scene",
        "create_plot",
        "create_shots",
        "create_frames",
        "create_video_clips",
        "persist_plan",
        "parse_brief",
        "update_script",
        "update_plot",
        "update_character",
        "update_scene",
        "update_prop",
        "delete_character",
        "delete_plot",
        "delete_scene",
        "delete_prop",
        "load_shots",
        "load_context",
        "load_edit_context",
        "plan_edit_timeline",
        "gather_media",
        "persist_review",
        "review_shot",
        "review_and_restructure",
        # analyze_edit_timeline 在矩阵中单独覆盖
        # OpenCut 变更由专用测试覆盖（避免同 store 内 remove 影响后续 clip）
        "add_clip",
        "update_clip",
        "remove_clip",
        "apply_effect",
        "set_keyframe",
    }
)

# 允许 result.ok=False 但仍须校验 structured 的 tool（无 — 全部跳过或 ok 才校验）
_OK_FALSE_ALLOWED = frozenset({"validate_edit_assets"})

# context/read 类 tool 的 output required 不得含 action
_CONTEXT_READ_NO_ACTION = frozenset(
    {
        "get_shot_details",
        "get_shot_asset_timing",
        "sync_actual_assets",
        "get_refine_plan",
        "update_frames",
        "get_plan",
        "get_export_status",
        "list_text_assets",
        "list_images",
        "list_videos",
        "list_audio",
        "list_final",
        "scan_text_assets",
        "get_edit_timeline",
        "validate_edit_assets",
    }
)


def _build_timeline_store() -> tuple[MemoryStore, str, str, str, str]:
    """构建含 VideoPlan、EditTimeline 与媒体的最小 store。"""
    store = MemoryStore()
    project = Project(title="schema-matrix")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1", duration_sec=30)
    store.add_script(script)
    prop = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.PROP,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="道具",
        content=prop_content(summary="道具"),
    )
    store.add_text_asset(prop)
    media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="道具图",
        url="https://images.test/prop.png",
        source_asset_id=prop.id,
    )
    store.add_media_asset(media)
    prop.primary_media_id = media.id
    store.update_text_asset(prop)
    shot = Shot(
        order=0,
        duration_ms=4000,
        narration_text="展示道具",
        asset_refs={"prop": [prop.id]},
    )
    ensure_shot_frame_image(
        store,
        project_id=project.id,
        script_id=script.id,
        shot=shot,
        image_url="https://images.test/frame.png",
    )
    plan = VideoPlan(
        script_id=script.id,
        mode=VideoStyleMode.STORYBOOK,
        shots=[shot],
    )
    store.set_video_plan(plan)
    timeline = compile_timeline_from_shots(
        store,
        script_id=script.id,
        plan=plan,
    )
    store.set_edit_timeline(timeline)
    clip_id = timeline.video_layers[0].clips[0].id if timeline.video_layers else ""
    return store, project.id, script.id, media.id, clip_id


def _ctx(script_id: str, project_id: str, agent: str) -> AgentRunContext:
    """构建带 project/script 的 AgentRunContext。"""
    return AgentRunContext(
        script_id=script_id,
        conversation_id="conv_schema",
        step_id="step_schema",
        task_brief="schema matrix",
        agent_name=agent,
        work_context={"project_id": project_id, "script_id": script_id},
        outputs=[],
    )


def _tool_args(
    name: str,
    *,
    script_id: str,
    project_id: str,
    media_id: str,
    clip_id: str,
    job_id: str,
) -> dict:
    """按 tool 名返回最小合法入参。"""
    base = {"observation": f"测试 {name}", **_PLAN_TRACKING}
    if name == "get_export_status":
        return {"job_id": job_id, **base}
    if name == "analyze_edit_timeline":
        return {**base, "start_ms": 0, "end_ms": 4000, "include_analysis": False}
    if name == "add_clip":
        return {
            **base,
            "media_id": media_id,
            "track": "video",
            "start_ms": 0,
            "duration_ms": 2000,
        }
    if name == "update_clip":
        return {**base, "clip_id": clip_id, "label": "更新标签"}
    if name == "remove_clip":
        return {**base, "clip_id": clip_id}
    if name == "apply_effect":
        return {**base, "clip_id": clip_id, "effect_type": "blur", "params": {}}
    if name == "set_keyframe":
        return {
            **base,
            "clip_id": clip_id,
            "time_ms": 500,
            "properties": {"opacity": 0.8},
        }
    if name == "parse_brief":
        return {**base, "content_md": "# 标题\n\n正文"}
    if name == "create_plot":
        return {**base, "content": {"text": "剧情摘要"}}
    if name == "create_character":
        return {
            **base,
            "content": {
                "summary": "角色",
                "description": "角色描述" * 5,
                "tts_voice": "zh_female",
            },
        }
    if name in ("create_prop", "create_scene"):
        return {
            **base,
            "content": {"summary": "资产", "description": "描述" * 5},
        }
    if name in ("update_plot", "update_character", "update_scene", "update_prop"):
        return {**base, "asset_id": "missing", "content": {"summary": "x"}}
    if name in ("delete_plot", "delete_character", "delete_scene", "delete_prop"):
        return {**base, "asset_id": "missing"}
    if name in ("create_shots", "create_frames", "persist_plan"):
        return {**base, "shots": []}
    if name in ("persist_review", "review_and_restructure", "review_shot"):
        return {**base, "patches": [], "restructure_ops": []}
    if name == "analyze_av_sync":
        return {**base, "mode": "analyze_only"}
    if name == "plan_edit_timeline":
        return {**base, "tracks": {"video": [], "audio": [], "subtitle": []}}
    if name == "gather_media":
        return base
    if name == "update_script":
        return {**base, "title": "新标题"}
    return base


def test_output_schema_for_matches_registry():
    """注册时 output_schema 须与 output_schema_for 一致，防止漂移。"""
    reset_tool_registry()
    registry = get_tool_registry()
    drift: list[str] = []
    for spec in registry.list_tools():
        expected = output_schema_for(spec.name)
        if spec.output_schema != expected:
            drift.append(
                f"{spec.name}: registered required={spec.output_schema.get('required')} "
                f"expected required={expected.get('required')}"
            )
    assert not drift, "output_schema 漂移:\n" + "\n".join(drift)


def test_no_generic_output_for_context_tools():
    """context/read tool 的 output required 不得含 action。"""
    reset_tool_registry()
    registry = get_tool_registry()
    for spec in registry.list_tools():
        if spec.name not in _CONTEXT_READ_NO_ACTION:
            continue
        required = spec.output_schema.get("required") or []
        assert "action" not in required, (
            f"{spec.name} 不应要求 action，实际 required={required}"
        )


def test_update_frames_not_asset_mutation():
    """update_frames 不得被 startswith update_ 误匹配为 asset_mutation。"""
    schema = output_schema_for("update_frames")
    required = schema.get("required", [])
    assert "updated_frame_count" in required
    assert "asset_id" not in required
    assert "action" not in required


@pytest.mark.asyncio
async def test_all_callable_tools_output_schema_matrix():
    """可本地执行的 tool 须 result.ok 且 structured 通过 output_schema。"""
    reset_tool_registry()
    registry = get_tool_registry()
    store, project_id, script_id, media_id, clip_id = _build_timeline_store()
    job = create_export_job(project_id, script_id)
    failures: list[str] = []

    for spec in registry.list_tools():
        if spec.name in _SKIP_CALL_MATRIX:
            continue
        ctx = _ctx(script_id, project_id, spec.agent)
        args = _tool_args(
            spec.name,
            script_id=script_id,
            project_id=project_id,
            media_id=media_id,
            clip_id=clip_id,
            job_id=job.id,
        )
        try:
            result = await registry.call_tool(spec.name, args, ctx, store)
        except Exception as exc:
            failures.append(f"{spec.name}: raised {type(exc).__name__}: {exc}")
            continue
        if not result.ok:
            if spec.name in _OK_FALSE_ALLOWED:
                continue
            if spec.name.startswith(("update_", "delete_")) and "不存在" in result.observation:
                continue
            failures.append(f"{spec.name}: not ok — {result.observation[:200]}")
            continue
        try:
            jsonschema.validate(instance=result.structured, schema=spec.output_schema)
        except jsonschema.ValidationError as exc:
            failures.append(f"{spec.name}: output validate — {exc.message}")

    assert not failures, "output schema 矩阵失败:\n" + "\n".join(failures)


@pytest.mark.asyncio
async def test_opencut_clip_tools_output_schema():
    """OpenCut 片段变更 tool 输出须含 action 与 clip_id。"""
    reset_tool_registry()
    registry = get_tool_registry()
    store, project_id, script_id, media_id, clip_id = _build_timeline_store()
    ctx = _ctx(script_id, project_id, "editing_agent")

    add_result = await registry.call_tool(
        "add_clip",
        {
            "observation": "添加",
            **_PLAN_TRACKING,
            "media_id": media_id,
            "track": "video",
            "start_ms": 100,
            "duration_ms": 1500,
        },
        ctx,
        store,
    )
    assert add_result.ok, add_result.observation
    assert add_result.structured["action"] == "add_clip"
    assert add_result.structured["clip_id"]

    new_clip_id = add_result.structured["clip_id"]
    update_result = await registry.call_tool(
        "update_clip",
        {"observation": "更新", **_PLAN_TRACKING, "clip_id": new_clip_id, "label": "新名"},
        ctx,
        store,
    )
    assert update_result.ok, update_result.observation
    assert update_result.structured["action"] == "update_clip"

    export_job = create_export_job(project_id, script_id)
    status_result = await registry.call_tool(
        "get_export_status",
        {"observation": "查进度", **_PLAN_TRACKING, "job_id": export_job.id},
        ctx,
        store,
    )
    assert status_result.ok, status_result.observation
    assert "action" not in status_result.structured
    assert status_result.structured["job_id"] == export_job.id
