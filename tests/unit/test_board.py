"""看板构建单元测试。"""

import pytest

from core.board.builder import BoardBuilder, BOARD_KINDS
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
from core.edit.timeline import compile_timeline_from_shots
from core.store.memory import MemoryStore


@pytest.fixture
def sample_store() -> MemoryStore:
    store = MemoryStore()
    project = Project(title="测试项目")
    store.add_project(project)
    script = Script(project_id=project.id, title="第一集", content_md="# 开场\n\n故事开始")
    store.add_script(script)

    char = TextAsset(
        project_id=project.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.PROJECT_SHARED,
        name="主角",
        content={"appearance": "年轻程序员"},
        source_script_id=script.id,
    )
    store.add_text_asset(char)

    plot = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.PLOT,
        name="开场",
        content={"text": "故事开始"},
    )
    store.add_text_asset(plot)

    vp = VideoPlan(
        script_id=script.id,
        mode=VideoStyleMode.DYNAMIC_IMAGE,
        shots=[
            VideoPlanShot(order=0, narration_text="你好世界", duration_ms=3000),
        ],
    )
    store.set_video_plan(vp)

    store.add_media_asset(
        MediaAsset(
            project_id=project.id,
            script_id=script.id,
            type=MediaAssetType.IMAGE,
            name="主角图",
            url="https://cdn.example.com/hero.png",
            source_asset_id=char.id,
        )
    )

    return store


@pytest.mark.parametrize("kind", BOARD_KINDS)
def test_build_all_board_kinds(sample_store: MemoryStore, kind: str):
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    view = BoardBuilder(sample_store).build(kind, project_id, script_id)
    assert view.kind == kind
    assert view.title


def test_overview_lists_scripts(sample_store: MemoryStore):
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    view = BoardBuilder(sample_store).build("overview", project_id, script_id)
    assert len(view.items) == 1
    assert view.items[0]["title"] == "第一集"


def test_character_board_links_image(sample_store: MemoryStore):
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    view = BoardBuilder(sample_store).build("character", project_id, script_id)
    assert len(view.items) == 1
    assert view.items[0]["images"]
    assert view.items[0]["description"]


def test_project_graph_has_edges(sample_store: MemoryStore):
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    view = BoardBuilder(sample_store).build("project_graph", project_id, script_id)
    assert len(view.nodes) >= 3
    assert len(view.edges) >= 2


def test_pipeline_order(sample_store: MemoryStore):
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    view = BoardBuilder(sample_store).build("pipeline", project_id, script_id)
    assert view.pipeline
    assert view.pipeline[0].step_type == "script_design"


def test_edit_board_shows_timeline_tracks(sample_store: MemoryStore):
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    plan = sample_store.get_video_plan_for_script(script_id)
    assert plan
    timeline = compile_timeline_from_shots(sample_store, script_id=script_id, plan=plan)
    sample_store.set_edit_timeline(timeline)
    view = BoardBuilder(sample_store).build("edit", project_id, script_id)
    assert view.kind == "edit"
    assert view.stats
    assert view.stats.get("video_clips", 0) >= 1
    assert "tracks" in view.stats


def test_script_details_board(sample_store: MemoryStore):
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    view = BoardBuilder(sample_store).build("script_details", project_id, script_id)
    assert view.kind == "script_details"
    assert len(view.items) == 1
    assert view.items[0]["title"] == "第一集"
    assert view.stats
    assert view.stats.get("content_md")


def test_storyboard_board_timing_and_fields(sample_store: MemoryStore):
    """分镜看板应含累计时间与角色名。"""
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    char_id = next(
        a.id for a in sample_store.text_assets.values() if a.type == TextAssetType.CHARACTER
    )
    vp = sample_store.get_video_plan_for_script(script_id)
    assert vp is not None
    vp.shots[0].asset_refs = {"character": [char_id]}
    vp.shots.append(
        VideoPlanShot(order=1, narration_text="第二镜", duration_ms=2000, camera_motion="pan_left")
    )
    sample_store.set_video_plan(vp)

    view = BoardBuilder(sample_store).build("storyboard", project_id, script_id)
    assert len(view.items) == 2
    first = view.items[0]
    second = view.items[1]
    assert first["start_ms"] == 0
    assert first["end_ms"] == 3000
    assert first["time_label"] == "0:00.0 – 0:03.0"
    assert second["start_ms"] == 3000
    assert second["end_ms"] == 5000
    assert first.get("character_names") == ["主角"]


def test_storyboard_board_follows_edit_timeline_clip(sample_store: MemoryStore):
    """有 EditTimeline 且 clip 拖拽后，看板时间应跟随真实 clip。"""
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    plan = sample_store.get_video_plan_for_script(script_id)
    assert plan
    timeline = compile_timeline_from_shots(sample_store, script_id=script_id, plan=plan)
    layer = timeline.video_layers[0]
    shot = plan.shots[0]
    shifted = layer.clips[0].model_copy(update={"start_ms": 500, "end_ms": 3500})
    timeline = timeline.model_copy(
        update={"video_layers": [layer.model_copy(update={"clips": [shifted]})]}
    )
    sample_store.set_edit_timeline(timeline)

    view = BoardBuilder(sample_store).build("storyboard", project_id, script_id)
    item = view.items[0]
    assert item["start_ms"] == 500
    assert item["end_ms"] == 3500
    assert item["timeline_source"] == "edit_timeline"


def test_storyboard_board_subtitle_absolute_times(sample_store: MemoryStore):
    """分镜看板应暴露句级字幕绝对时间。"""
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    plan = sample_store.get_video_plan_for_script(script_id)
    assert plan
    shot = plan.shots[0]

    audio = MediaAsset(
        project_id=project_id,
        script_id=script_id,
        type=MediaAssetType.AUDIO,
        name="配音",
        url="https://cdn.example.com/tts.mp3",
        metadata={
            "shot_id": shot.id,
            "duration_ms": 3000,
            "subtitle_cues": [
                {"text": "你好", "start_ms": 0, "end_ms": 1000},
                {"text": "世界", "start_ms": 1000, "end_ms": 3000},
            ],
        },
    )
    sample_store.add_media_asset(audio)

    timeline = compile_timeline_from_shots(sample_store, script_id=script_id, plan=plan)
    audio_clip = timeline.tracks["audio"][0].model_copy(update={"start_ms": 1000, "end_ms": 4000})
    timeline = timeline.model_copy(
        update={"tracks": {**timeline.tracks, "audio": [audio_clip]}}
    )
    sample_store.set_edit_timeline(timeline)

    view = BoardBuilder(sample_store).build("storyboard", project_id, script_id)
    lines = view.items[0].get("subtitle_lines") or []
    assert len(lines) == 2
    assert lines[0]["absolute_start_ms"] == 1000
    assert lines[1]["absolute_end_ms"] == 4000
