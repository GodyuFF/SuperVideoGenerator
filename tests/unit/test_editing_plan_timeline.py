"""editing_agent plan_edit_timeline 与 load_edit_context 测试。"""

import pytest

from core.edit.timeline import compile_timeline_from_shots, flat_video_clips
from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.editing.context import build_edit_context_payload
from core.llm.tools.output_schemas import (
    generic_action_output_schema,
    load_edit_context_output_schema,
    validate_edit_assets_output_schema,
)
from core.llm.tools.editing.timeline_handler import (
    handle_analyze_edit_timeline,
    handle_get_edit_timeline,
    handle_load_edit_context,
    handle_plan_edit_timeline,
    handle_validate_edit_assets,
)
from core.llm.tools.register_helpers import output_schema_for
from core.llm.tools.validators import validate_against_schema
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


@pytest.fixture
def editing_store() -> MemoryStore:
    store = MemoryStore()
    project = Project(title="剪辑测试")
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
    from core.models.entities import ShotSubShot

    shot = Shot(
        order=0,
        duration_ms=4000,
        sub_shots=[
            ShotSubShot(
                start_ms=0,
                end_ms=4000,
                description="展示道具",
                element_refs={"prop": [prop.id]},
                camera_motion="ken_burns_in",
            )
        ],
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
    store._test_script_id = script.id  # type: ignore[attr-defined]
    store._test_project_id = project.id  # type: ignore[attr-defined]
    store._test_shot_id = shot.id  # type: ignore[attr-defined]
    store._test_media_id = media.id  # type: ignore[attr-defined]
    return store


def test_load_edit_context_includes_plan_and_media(editing_store: MemoryStore):
    script_id = editing_store._test_script_id  # type: ignore[attr-defined]
    payload = build_edit_context_payload(editing_store, script_id)
    assert payload["video_plan"]["shot_count"] == 1
    assert payload["media"]
    assert payload["text_assets"]
    assert "content_md" in payload["script"]
    assert payload["assets_with_images"]
    assert payload["linked_image_count"] >= 1
    shot = payload["video_plan"]["shots"][0]
    assert "sub_shots" in shot
    assert shot["resolved"]["image_media_id"]
    assert shot["resolved"]["image_accessible"] is True
    assert "subtitle_style_context" in payload
    assert payload["subtitle_style_context"]["subtitle_style"]["placement"] == "bottom_center"


def test_output_schema_for_load_edit_context():
    schema = output_schema_for("load_edit_context")
    assert schema is not generic_action_output_schema()
    assert "action" in schema.get("required", [])


def test_load_edit_context_structured_passes_schema(editing_store: MemoryStore):
    script_id = editing_store._test_script_id  # type: ignore[attr-defined]
    project_id = editing_store._test_project_id  # type: ignore[attr-defined]
    shot_id = editing_store._test_shot_id  # type: ignore[attr-defined]
    audio = MediaAsset(
        project_id=project_id,
        script_id=script_id,
        type=MediaAssetType.AUDIO,
        name="旁白",
        url="https://audio.test/narration.mp3",
        metadata={"shot_id": shot_id, "duration_ms": 4000},
    )
    editing_store.add_media_asset(audio)

    ctx = AgentRunContext(
        task_brief="加载剪辑上下文",
        work_context={"style_mode": VideoStyleMode.STORYBOOK},
        script_id=script_id,
        step_id="edit_compose",
        agent_name="editing_agent",
        project_id=project_id,
    )
    result = handle_load_edit_context(
        editing_store,
        ctx,
        {
            "observation": "加载上下文",
            "plan_status": "加载中",
            "remaining_plan": ["plan_edit_timeline"],
        },
    )
    assert result.ok is True
    assert result.structured is not None
    assert result.structured.get("action") == "load_edit_context"
    validate_against_schema(
        result.structured,
        load_edit_context_output_schema(),
        label="输出",
    )
    shot = result.structured["video_plan"]["shots"][0]
    assert shot["resolved"]["audio_media_id"] == audio.id
    assert shot["resolved"]["audio_accessible"] is True
    assert ctx.work_context.get("edit_context") is not None


def test_plan_edit_timeline_merges_llm_tracks_with_plan(editing_store: MemoryStore):
    script_id = editing_store._test_script_id  # type: ignore[attr-defined]
    project_id = editing_store._test_project_id  # type: ignore[attr-defined]
    shot_id = editing_store._test_shot_id  # type: ignore[attr-defined]
    media_id = editing_store._test_media_id  # type: ignore[attr-defined]

    ctx = AgentRunContext(
        task_brief="生成剪辑计划稿",
        work_context={"style_mode": VideoStyleMode.STORYBOOK},
        script_id=script_id,
        step_id="edit_compose",
        agent_name="editing_agent",
        project_id=project_id,
    )
    result = handle_plan_edit_timeline(
        editing_store,
        ctx,
        {
            "observation": "已规划三轨",
            "tracks": {
                "video": [
                    {
                        "track": "video",
                        "start_ms": 0,
                        "end_ms": 4000,
                        "label": "道具特写",
                        "asset_ref": media_id,
                        "edit_description": "Ken Burns 推近道具",
                        "motion_detail": {
                            "type": "ken_burns_in",
                            "from_focal": [0.2, 0.3],
                            "to_focal": [0.5, 0.5],
                        },
                        "transition_in": {"type": "fade", "duration_ms": 200},
                        "source_refs": {
                            "shot_id": shot_id,
                            "video_plan_shot_order": 0,
                        },
                    }
                ],
                "audio": [
                    {
                        "track": "audio",
                        "start_ms": 0,
                        "end_ms": 4000,
                        "label": "旁白",
                        "metadata": {"shot_id": shot_id},
                    }
                ],
                "subtitle": [
                    {
                        "track": "subtitle",
                        "start_ms": 0,
                        "end_ms": 4000,
                        "label": "展示道具",
                    }
                ],
            },
        },
    )
    assert result.ok is True
    timeline = editing_store.get_edit_timeline_for_script(script_id)
    assert timeline is not None
    assert timeline.duration_ms == 4000
    video_clip = flat_video_clips(timeline)[0]
    assert video_clip.edit_description == "Ken Burns 推近道具"
    assert video_clip.motion_detail is not None
    assert video_clip.source_refs is not None
    assert video_clip.source_refs.shot_id == shot_id


def test_plan_edit_timeline_video_layers(editing_store: MemoryStore):
    script_id = editing_store._test_script_id  # type: ignore[attr-defined]
    project_id = editing_store._test_project_id  # type: ignore[attr-defined]
    shot_id = editing_store._test_shot_id  # type: ignore[attr-defined]
    media_id = editing_store._test_media_id  # type: ignore[attr-defined]

    ctx = AgentRunContext(
        task_brief="生成多图层剪辑计划",
        work_context={"style_mode": VideoStyleMode.STORYBOOK},
        script_id=script_id,
        step_id="edit_compose",
        agent_name="editing_agent",
        project_id=project_id,
    )
    result = handle_plan_edit_timeline(
        editing_store,
        ctx,
        {
            "observation": "主画面 + 画中画",
            "video_layers": [
                {
                    "name": "主画面",
                    "z_index": 0,
                    "clips": [
                        {
                            "track": "video",
                            "start_ms": 0,
                            "end_ms": 4000,
                            "label": "道具全景",
                            "asset_ref": media_id,
                            "transform": {"x": 0.5, "y": 0.5, "width": 1.0, "height": 1.0},
                            "source_refs": {"shot_id": shot_id, "video_plan_shot_order": 0},
                        }
                    ],
                },
                {
                    "name": "画中画",
                    "z_index": 1,
                    "clips": [
                        {
                            "track": "video",
                            "start_ms": 500,
                            "end_ms": 3500,
                            "label": "道具特写",
                            "asset_ref": media_id,
                            "transform": {"x": 0.8, "y": 0.2, "width": 0.25, "height": 0.25},
                        }
                    ],
                },
            ],
            "tracks": {
                "audio": [
                    {
                        "track": "audio",
                        "start_ms": 0,
                        "end_ms": 4000,
                        "label": "旁白",
                        "metadata": {"shot_id": shot_id},
                    }
                ],
                "subtitle": [
                    {
                        "track": "subtitle",
                        "start_ms": 0,
                        "end_ms": 4000,
                        "label": "展示道具",
                    }
                ],
            },
        },
    )
    assert result.ok is True
    timeline = editing_store.get_edit_timeline_for_script(script_id)
    assert timeline is not None
    assert len(timeline.video_layers) == 2
    layers = sorted(timeline.video_layers, key=lambda item: item.z_index)
    assert layers[0].z_index == 0
    assert layers[1].z_index == 1
    pip_clip = layers[1].clips[0]
    assert pip_clip.transform is not None
    assert pip_clip.transform.width == 0.25
    assert result.structured.get("layer_summary")
    assert result.structured["layer_summary"]["video_layers"]
    assert len(result.structured["layer_summary"]["video_layers"]) == 2


def test_load_edit_context_includes_layer_summary(editing_store: MemoryStore):
    script_id = editing_store._test_script_id  # type: ignore[attr-defined]
    project_id = editing_store._test_project_id  # type: ignore[attr-defined]
    shot_id = editing_store._test_shot_id  # type: ignore[attr-defined]
    media_id = editing_store._test_media_id  # type: ignore[attr-defined]
    ctx = AgentRunContext(
        task_brief="规划",
        work_context={"style_mode": VideoStyleMode.STORYBOOK},
        script_id=script_id,
        step_id="edit_compose",
        agent_name="editing_agent",
        project_id=project_id,
    )
    handle_plan_edit_timeline(
        editing_store,
        ctx,
        {
            "video_layers": [
                {
                    "name": "主画面",
                    "z_index": 0,
                    "clips": [
                        {
                            "track": "video",
                            "start_ms": 0,
                            "end_ms": 4000,
                            "asset_ref": media_id,
                            "transform": {"x": 0.5, "y": 0.5, "width": 1.0, "height": 1.0},
                            "source_refs": {"shot_id": shot_id},
                        }
                    ],
                }
            ],
            "tracks": {"audio": [], "subtitle": []},
        },
    )
    payload = build_edit_context_payload(editing_store, script_id)
    edit_tl = payload["edit_timeline"]
    assert edit_tl is not None
    assert edit_tl["layer_summary"]
    assert edit_tl["layer_summary"]["video_layers"][0]["clips"][0]["transform"]


def test_plan_edit_timeline_observation_lists_all_warnings(editing_store: MemoryStore):
    script_id = editing_store._test_script_id  # type: ignore[attr-defined]
    project_id = editing_store._test_project_id  # type: ignore[attr-defined]
    media_id = editing_store._test_media_id  # type: ignore[attr-defined]
    ctx = AgentRunContext(
        task_brief="重叠测试",
        work_context={"style_mode": VideoStyleMode.STORYBOOK},
        script_id=script_id,
        step_id="edit_compose",
        agent_name="editing_agent",
        project_id=project_id,
    )
    result = handle_plan_edit_timeline(
        editing_store,
        ctx,
        {
            "video_layers": [
                {
                    "name": "PiP",
                    "z_index": 0,
                    "clips": [
                        {
                            "track": "video",
                            "start_ms": 0,
                            "end_ms": 4000,
                            "asset_ref": media_id,
                        },
                        {
                            "track": "video",
                            "start_ms": 3000,
                            "end_ms": 5000,
                            "asset_ref": media_id,
                        },
                    ],
                }
            ],
            "tracks": {"audio": [], "subtitle": []},
        },
    )
    assert result.ok is True
    video_warnings = [
        w for w in result.structured["warnings"] if "与同层片段重叠" in w
    ]
    assert video_warnings
    for warning in video_warnings:
        assert warning in result.observation


def test_validate_edit_assets_output_schema_matches_handler(editing_store: MemoryStore):
    """validate_edit_assets 输出须通过专用 schema 校验。"""
    script_id = editing_store._test_script_id  # type: ignore[attr-defined]
    project_id = editing_store._test_project_id  # type: ignore[attr-defined]
    ctx = AgentRunContext(
        task_brief="校验素材",
        work_context={"style_mode": VideoStyleMode.STORYBOOK},
        script_id=script_id,
        step_id="edit_compose",
        agent_name="editing_agent",
        project_id=project_id,
    )
    handle_plan_edit_timeline(
        editing_store,
        ctx,
        {
            "observation": "规划",
            "mode": "create",
            "video_layers": [
                {
                    "id": "layer_main",
                    "name": "主层",
                    "z_index": 0,
                    "clips": [
                        {
                            "id": "clip_v1",
                            "start_ms": 0,
                            "end_ms": 4000,
                            "asset_ref": editing_store._test_media_id,  # type: ignore[attr-defined]
                        }
                    ],
                }
            ],
        },
    )
    result = handle_validate_edit_assets(editing_store, ctx, {"observation": "校验"})
    schema = validate_edit_assets_output_schema()
    validate_against_schema(result.structured, schema, label="输出")
    assert output_schema_for("validate_edit_assets") == schema


def test_plan_edit_timeline_replace_empty_subtitle_skips_enrich(editing_store: MemoryStore):
    """replace 模式显式空 subtitle 轨时不自动回填 TTS 字幕。"""
    script_id = editing_store._test_script_id  # type: ignore[attr-defined]
    project_id = editing_store._test_project_id  # type: ignore[attr-defined]
    ctx = AgentRunContext(
        task_brief="规划无字幕轨",
        work_context={"style_mode": VideoStyleMode.STORYBOOK},
        script_id=script_id,
        step_id="edit_compose",
        agent_name="editing_agent",
        project_id=project_id,
    )
    audio = MediaAsset(
        project_id=editing_store._test_project_id,  # type: ignore[attr-defined]
        script_id=script_id,
        type=MediaAssetType.AUDIO,
        name="tts",
        url="https://audio.test/tts.mp3",
        metadata={
            "shot_id": editing_store._test_shot_id,  # type: ignore[attr-defined]
            "duration_ms": 4000,
            "subtitle_cues": [{"start_ms": 0, "end_ms": 1000, "text": "第一句"}],
        },
    )
    editing_store.add_media_asset(audio)
    result = handle_plan_edit_timeline(
        editing_store,
        ctx,
        {
            "observation": "无字幕轨",
            "mode": "replace",
            "tracks": {"audio": [], "subtitle": []},
            "video_layers": [
                {
                    "id": "layer_main",
                    "name": "主层",
                    "z_index": 0,
                    "clips": [
                        {
                            "id": "clip_v1",
                            "start_ms": 0,
                            "end_ms": 4000,
                            "asset_ref": editing_store._test_media_id,  # type: ignore[attr-defined]
                        }
                    ],
                }
            ],
        },
    )
    assert result.ok is True
    timeline = editing_store.get_edit_timeline_for_script(script_id)
    assert timeline is not None
    assert timeline.tracks.get("subtitle") == []


def test_analyze_edit_timeline_tool(editing_store: MemoryStore):
    """analyze_edit_timeline 应返回区间分析与分镜对齐。"""
    script_id = editing_store._test_script_id  # type: ignore[attr-defined]
    project_id = editing_store._test_project_id  # type: ignore[attr-defined]
    plan = editing_store.get_video_plan_for_script(script_id)
    assert plan
    timeline = compile_timeline_from_shots(editing_store, script_id=script_id, plan=plan)
    editing_store.set_edit_timeline(timeline)
    ctx = AgentRunContext(
        task_brief="分析剪辑",
        work_context={"style_mode": VideoStyleMode.STORYBOOK},
        script_id=script_id,
        step_id="edit_compose",
        agent_name="editing_agent",
        project_id=project_id,
    )
    result = handle_analyze_edit_timeline(
        editing_store,
        ctx,
        {"observation": "检查前 2 秒", "start_ms": 0, "end_ms": 2000},
    )
    assert result.ok is True
    structured = result.structured
    assert structured["action"] == "analyze_edit_timeline"
    assert structured["range"]["end_ms"] == 2000
    assert "clips_in_range" in structured
    assert structured["shot_alignment"]
    video_clips = [c for c in structured["clips_in_range"] if c.get("track") == "video"]
    assert video_clips
    assert "visible_range" in video_clips[0]
    assert "edit_description" in video_clips[0]


def test_analyze_edit_timeline_detail_only(editing_store: MemoryStore):
    """include_analysis=false 时仅返回 clip 详情，不含 alignment/hints。"""
    script_id = editing_store._test_script_id  # type: ignore[attr-defined]
    project_id = editing_store._test_project_id  # type: ignore[attr-defined]
    plan = editing_store.get_video_plan_for_script(script_id)
    assert plan
    timeline = compile_timeline_from_shots(editing_store, script_id=script_id, plan=plan)
    editing_store.set_edit_timeline(timeline)
    ctx = AgentRunContext(
        task_brief="读取详情",
        work_context={"style_mode": VideoStyleMode.STORYBOOK},
        script_id=script_id,
        step_id="edit_compose",
        agent_name="editing_agent",
        project_id=project_id,
    )
    result = handle_analyze_edit_timeline(
        editing_store,
        ctx,
        {
            "observation": "读 0-2 秒详情",
            "start_ms": 0,
            "end_ms": 2000,
            "include_analysis": False,
        },
    )
    assert result.ok is True
    structured = result.structured
    assert structured["clips_in_range"]
    assert structured["shot_alignment"] == []
    assert structured["optimization_hints"] == []


def test_load_edit_context_includes_shot_timings(editing_store: MemoryStore):
    """load_edit_context 的 shots 应含 timeline 与 subtitle_lines。"""
    script_id = editing_store._test_script_id  # type: ignore[attr-defined]
    plan = editing_store.get_video_plan_for_script(script_id)
    assert plan
    timeline = compile_timeline_from_shots(editing_store, script_id=script_id, plan=plan)
    editing_store.set_edit_timeline(timeline)
    payload = build_edit_context_payload(editing_store, script_id)
    shots = payload["video_plan"]["shots"]
    assert shots[0]["timeline_start_ms"] is not None
    assert shots[0]["timeline_end_ms"] is not None
    assert payload["edit_timeline"]["analyze_summary"]


def test_get_edit_timeline_matches_store_after_plan(editing_store: MemoryStore):
    """get_edit_timeline 与 store 中 EditTimeline 须为同一 revision 数据。"""
    script_id = editing_store._test_script_id  # type: ignore[attr-defined]
    project_id = editing_store._test_project_id  # type: ignore[attr-defined]
    shot_id = editing_store._test_shot_id  # type: ignore[attr-defined]
    media_id = editing_store._test_media_id  # type: ignore[attr-defined]
    ctx = AgentRunContext(
        task_brief="规划",
        work_context={"style_mode": VideoStyleMode.STORYBOOK},
        script_id=script_id,
        step_id="edit_compose",
        agent_name="editing_agent",
        project_id=project_id,
    )
    handle_plan_edit_timeline(
        editing_store,
        ctx,
        {
            "video_layers": [
                {
                    "name": "主画面",
                    "z_index": 0,
                    "clips": [
                        {
                            "track": "video",
                            "start_ms": 0,
                            "end_ms": 4000,
                            "asset_ref": media_id,
                            "source_refs": {"shot_id": shot_id, "video_plan_shot_order": 0},
                        }
                    ],
                }
            ],
            "tracks": {"audio": [], "subtitle": []},
        },
    )
    stored = editing_store.get_edit_timeline_for_script(script_id)
    assert stored is not None
    result = handle_get_edit_timeline(editing_store, ctx, {})
    assert result.structured["duration_ms"] == stored.duration_ms
    assert result.structured["revision"] == stored.revision
    assert len(result.structured["layer_summary"]["video_layers"]) == len(stored.video_layers)


def test_compile_timeline_uses_video_clip_camera_motion(editing_store: MemoryStore):
    """compile_timeline_from_shots 应使用镜内视频 clip 的运镜。"""
    from core.models.entities import ShotVideoClip, ShotVideoTrack

    script_id = editing_store._test_script_id  # type: ignore[attr-defined]
    plan = editing_store.get_video_plan_for_script(script_id)
    assert plan
    shot = plan.shots[0]
    shot = shot.model_copy(
        update={
            "video_tracks": [
                ShotVideoTrack(
                    z_index=0,
                    clips=[
                        ShotVideoClip(
                            start_ms=0,
                            end_ms=4000,
                            media_id=editing_store._test_media_id,  # type: ignore[attr-defined]
                            source_kind="still",
                            camera_motion="ken_burns_out",
                        )
                    ],
                )
            ]
        }
    )
    plan = plan.model_copy(update={"shots": [shot]})
    editing_store.set_video_plan(plan)
    timeline = compile_timeline_from_shots(editing_store, script_id=script_id, plan=plan)
    video_clip = flat_video_clips(timeline)[0]
    assert video_clip.motion == "ken_burns_out"

