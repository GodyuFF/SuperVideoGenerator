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
    Shot,
    VideoStyleMode,
)
from core.edit.timeline import compile_timeline_from_shots
from core.store.memory import MemoryStore
from tests.support.frame_fixtures import ensure_shot_frame_image
from tests.support.shot_fixtures import make_shot


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
        content={"description": "年轻程序员"},
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

    shot = make_shot(order=0, text="你好世界", duration_ms=3000)
    shot.sub_shots[0].element_refs = {"character": [char.id]}
    ensure_shot_frame_image(
        store,
        project_id=project.id,
        script_id=script.id,
        shot=shot,
        image_url="https://cdn.example.com/hero.png",
    )
    vp = VideoPlan(
        script_id=script.id,
        mode=VideoStyleMode.STORYBOOK,
        shots=[shot],
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
    assert view.items[0]["script_index"] == 1
    assert view.items[0]["order"] == 1


def test_overview_scripts_ordered_by_created_at():
    """整体看板按创建时间升序编号展示剧本。"""
    store = MemoryStore()
    project = Project(title="排序项目")
    store.add_project(project)
    later = Script(
        project_id=project.id,
        title="后建",
        created_at="2026-07-17T12:00:00+00:00",
    )
    earlier = Script(
        project_id=project.id,
        title="先建",
        created_at="2026-07-16T08:00:00+00:00",
    )
    store.add_script(later)
    store.add_script(earlier)

    view = BoardBuilder(store).build("overview", project.id, None)
    assert [i["title"] for i in view.items] == ["先建", "后建"]
    assert [i["script_index"] for i in view.items] == [1, 2]


def test_knowledge_board_enriches_script_links(sample_store: MemoryStore):
    """项目图文看板应附带引用剧本与来源剧本标题。"""
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    view = BoardBuilder(sample_store).build("knowledge", project_id, script_id)
    assert view.kind == "knowledge"
    assert view.items
    char = next(i for i in view.items if i.get("type") == "character")
    assert char.get("source_script_title") == "第一集"
    assert script_id in (char.get("referenced_script_ids") or [])
    stats = view.stats or {}
    assert "by_type" in stats
    assert stats["by_type"].get("character") == 1
    scripts = stats.get("scripts") or []
    assert any(s.get("id") == script_id and s.get("title") == "第一集" for s in scripts)


def test_knowledge_board_source_vs_reference_scripts():
    """来源剧本与引用剧本筛选字段应区分创建来源与分镜引用。"""
    store = MemoryStore()
    project = Project(title="多剧本项目")
    store.add_project(project)
    script_a = Script(project_id=project.id, title="剧本 A")
    script_b = Script(project_id=project.id, title="剧本 B")
    store.add_script(script_a)
    store.add_script(script_b)

    reused = TextAsset(
        project_id=project.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.PROJECT_SHARED,
        name="复用角色",
        content={"description": "跨剧本复用"},
        source_script_id=script_a.id,
    )
    store.add_text_asset(reused)

    only_source = TextAsset(
        project_id=project.id,
        type=TextAssetType.SCENE,
        scope=AssetScope.PROJECT_SHARED,
        name="仅来源空镜",
        content={"summary": "只在 A 创建"},
        source_script_id=script_a.id,
    )
    store.add_text_asset(only_source)

    shot = make_shot(order=0, text="引用镜", duration_ms=2000)
    shot.sub_shots[0].element_refs = {"character": [reused.id]}
    store.set_video_plan(
        VideoPlan(
            script_id=script_b.id,
            mode=VideoStyleMode.STORYBOOK,
            shots=[shot],
        )
    )

    view = BoardBuilder(store).build("knowledge", project.id, None)
    reused_item = next(i for i in view.items if i.get("name") == "复用角色")
    source_item = next(i for i in view.items if i.get("name") == "仅来源空镜")

    assert script_b.id in (reused_item.get("referenced_script_ids") or [])
    assert script_b.id not in (source_item.get("referenced_script_ids") or [])
    assert source_item.get("source_script_title") == "剧本 A"


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
    relations = {e.relation for e in (view.edges or [])}
    assert "generates" in relations


def test_media_board_includes_lineage_summary(sample_store: MemoryStore):
    """媒体看板条目应附带轻量 lineage_summary。"""
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    view = BoardBuilder(sample_store).build("media", project_id, script_id)
    assert view.items
    summary = view.items[0].get("lineage_summary")
    assert summary is not None
    assert "incoming_count" in summary
    assert "outgoing_count" in summary


def test_pipeline_board_empty_without_plan_steps(sample_store: MemoryStore):
    """无 Plan 步骤时 pipeline 看板不展示固定模板。"""
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    view = BoardBuilder(sample_store).build("pipeline", project_id, script_id)
    assert view.pipeline == []
    assert "非固定模板" in (view.description or "")


def test_pipeline_board_accepts_string_style_mode(sample_store: MemoryStore):
    """剧本 style_mode 持久化为字符串时，生成顺序看板应正常构建。"""
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    script = sample_store.get_script(script_id)
    assert script is not None
    script.style_mode = VideoStyleMode.STORYBOOK.value

    view = BoardBuilder(sample_store).build("pipeline", project_id, script_id)

    assert view.kind == "pipeline"
    assert view.stats.get("style_mode") == VideoStyleMode.STORYBOOK.value


def test_script_tab_visibility_has_edit_timeline(sample_store: MemoryStore):
    """有 EditTimeline 时 script meta 的 has_edit_timeline 为真（分镜剪辑轴门控依据）。"""
    builder = BoardBuilder(sample_store)
    script = next(iter(sample_store.scripts.values()))
    stats_before = builder._script_tab_visibility_stats(script.id)
    assert stats_before["has_edit_timeline"] is False

    plan = sample_store.get_video_plan_for_script(script.id)
    assert plan is not None
    timeline = compile_timeline_from_shots(
        sample_store, script_id=script.id, plan=plan
    )
    sample_store.set_edit_timeline(timeline)

    stats_after = builder._script_tab_visibility_stats(script.id)
    assert stats_after["has_edit_timeline"] is True


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
    assert len(view.items) >= 1
    script_row = next(i for i in view.items if i.get("script_id"))
    assert script_row["title"] == "第一集"
    plot_rows = [i for i in view.items if i.get("type") == "plot"]
    assert len(plot_rows) >= 1
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
    shot0 = vp.shots[0].model_copy(
        update={
            "sub_shots": [
                vp.shots[0].sub_shots[0].model_copy(
                    update={"element_refs": {"character": [char_id]}}
                )
            ]
        }
    )
    shot1 = make_shot(order=1, text="第二镜", duration_ms=2000, camera_motion="pan_left")
    sample_store.set_video_plan(vp.model_copy(update={"shots": [shot0, shot1]}))

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


def test_storyboard_board_follows_shot_structure(sample_store: MemoryStore):
    """看板时间来自镜内结构累加（plan_estimate）。"""
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    view = BoardBuilder(sample_store).build("storyboard", project_id, script_id)
    item = view.items[0]
    assert item["start_ms"] == 0
    assert item["end_ms"] == 3000
    assert item["timeline_source"] == "plan_estimate"


def test_storyboard_board_subtitle_absolute_times(sample_store: MemoryStore):
    """分镜看板应暴露镜内字幕绝对时间。"""
    from core.edit.shot_detail_sync import sync_plan_from_tts
    from core.models.entities import ShotSubtitle

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
    sync_plan_from_tts(sample_store, script_id)

    view = BoardBuilder(sample_store).build("storyboard", project_id, script_id)
    lines = view.items[0].get("subtitle_lines") or []
    assert len(lines) == 2
    assert lines[0]["absolute_start_ms"] == 0
    assert lines[1]["absolute_end_ms"] == 3000


def test_storyboard_board_after_tts_sync(sample_store: MemoryStore):
    """TTS 同步后分镜看板应展示镜内字幕与累加时间。"""
    from core.edit.shot_detail_sync import sync_plan_from_tts

    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    plan = sample_store.get_video_plan_for_script(script_id)
    assert plan
    shot = plan.shots[0]

    sample_store.add_media_asset(
        MediaAsset(
            project_id=project_id,
            script_id=script_id,
            type=MediaAssetType.AUDIO,
            name="配音",
            url="https://cdn.example.com/tts.mp3",
            metadata={
                "shot_id": shot.id,
                "duration_ms": 2500,
                "subtitle_cues": [{"text": "旁白", "start_ms": 0, "end_ms": 2500}],
            },
        )
    )
    sync_plan_from_tts(sample_store, script_id)

    view = BoardBuilder(sample_store).build("storyboard", project_id, script_id)
    item = view.items[0]
    assert item["start_ms"] == 0
    assert item["end_ms"] >= 2500
    assert item.get("subtitle_line_count", 0) >= 1


def test_storyboard_board_uses_plan_after_tts_sync_without_timeline_realign():
    """TTS 同步后看板时间来自分镜计划稿累加，不自动重排剪辑时间轴。"""
    from core.edit.shot_detail_sync import sync_plan_from_tts
    from tests.support.shot_fixtures import _store_with_two_shots

    store, script_id, shot1, shot2 = _store_with_two_shots()
    project_id = list(store.projects.keys())[0]
    plan = store.get_video_plan_for_script(script_id)
    assert plan
    stale = compile_timeline_from_shots(store, script_id=script_id, plan=plan)
    store.set_edit_timeline(stale)
    rev_before = stale.revision

    for shot, dur, text in (
        (shot1, 2500, "镜一"),
        (shot2, 4000, "镜二"),
    ):
        store.add_media_asset(
            MediaAsset(
                project_id=project_id,
                script_id=script_id,
                type=MediaAssetType.AUDIO,
                name=text,
                url=f"https://audio.test/{shot.id}.mp3",
                metadata={
                    "shot_id": shot.id,
                    "duration_ms": dur,
                    "subtitle_cues": [{"text": text, "start_ms": 0, "end_ms": dur}],
                },
            )
        )
    result = sync_plan_from_tts(store, script_id)
    assert "timeline_realigned" not in result
    timeline_after = store.get_edit_timeline_for_script(script_id)
    assert timeline_after is not None
    assert timeline_after.revision == rev_before

    view = BoardBuilder(store).build("storyboard", project_id, script_id)
    assert len(view.items) == 2
    items = sorted(view.items, key=lambda i: int(i.get("order") or 0))
    assert items[0]["start_ms"] == 0
    assert items[1]["start_ms"] == items[0]["end_ms"]
    assert items[0].get("timeline_source") == "plan_estimate"


def test_storyboard_board_repairs_non_monotonic_times(monkeypatch, sample_store: MemoryStore):
    """看板应修复多镜共用 start_ms=0 的非累加时间。"""
    from core.edit.shot_timing import ShotTimingView
    from core.models.entities import Shot

    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    vp = sample_store.get_video_plan_for_script(script_id)
    assert vp is not None
    shot2 = make_shot(order=1, text="第二镜", duration_ms=2000, camera_motion="ken_burns_pan")
    sample_store.set_video_plan(vp.model_copy(update={"shots": [vp.shots[0], shot2]}))

    def _bad_timings(store, script_id, **kwargs):
        return [
            ShotTimingView(
                shot_id=vp.shots[0].id,
                order=0,
                duration_ms=3000,
                timeline_start_ms=0,
                timeline_end_ms=3000,
                timeline_source="plan_estimate",
            ),
            ShotTimingView(
                shot_id=shot2.id,
                order=1,
                duration_ms=2000,
                timeline_start_ms=0,
                timeline_end_ms=2000,
                timeline_source="plan_estimate",
            ),
        ]

    monkeypatch.setattr("core.edit.shot_timing.resolve_shot_timings", _bad_timings)
    view = BoardBuilder(sample_store).build("storyboard", project_id, script_id)
    items = sorted(view.items, key=lambda i: int(i.get("order") or 0))
    assert items[0]["start_ms"] == 0
    assert items[1]["start_ms"] == items[0]["end_ms"]


def test_storyboard_board_lazy_tts_sync():
    """有 TTS 无镜内 voice 绑定时看板构建应懒同步。"""
    from tests.support.shot_fixtures import _store_with_two_shots

    store, script_id, shot1, shot2 = _store_with_two_shots()
    project_id = list(store.projects.keys())[0]
    for shot, dur, text in (
        (shot1, 2500, "镜一"),
        (shot2, 4000, "镜二"),
    ):
        store.add_media_asset(
            MediaAsset(
                project_id=project_id,
                script_id=script_id,
                type=MediaAssetType.AUDIO,
                name=text,
                url=f"https://audio.test/{shot.id}.mp3",
                metadata={
                    "shot_id": shot.id,
                    "duration_ms": dur,
                    "subtitle_cues": [{"text": text, "start_ms": 0, "end_ms": dur}],
                },
            )
        )
    view = BoardBuilder(store).build("storyboard", project_id, script_id)
    items = sorted(view.items, key=lambda i: int(i.get("order") or 0))
    assert items[0].get("tts_asset_id")
    assert items[1]["start_ms"] == items[0]["end_ms"]


def test_storyboard_board_scene_preview_fallback(sample_store: MemoryStore):
    """无 frame 仅有 scene 时，分镜看板不应把 scene 图填入画面预览。"""
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    scene = TextAsset(
        project_id=project_id,
        type=TextAssetType.SCENE,
        scope=AssetScope.PROJECT_SHARED,
        name="午后厨房",
        content={"summary": "厨房空镜"},
        source_script_id=script_id,
    )
    sample_store.add_text_asset(scene)
    sample_store.add_media_asset(
        MediaAsset(
            project_id=project_id,
            script_id=script_id,
            type=MediaAssetType.IMAGE,
            name="厨房图",
            url="https://cdn.example.com/kitchen.png",
            source_asset_id=scene.id,
        )
    )
    vp = sample_store.get_video_plan_for_script(script_id)
    assert vp
    shot = vp.shots[0].model_copy(
        update={
            "sub_shots": [
                vp.shots[0].sub_shots[0].model_copy(
                    update={
                        "element_refs": {"scene": [scene.id]},
                        "images": [],
                    }
                )
            ],
            "video_tracks": [],
        }
    )
    sample_store.set_video_plan(vp.model_copy(update={"shots": [shot]}))

    view = BoardBuilder(sample_store).build("storyboard", project_id, script_id)
    item = view.items[0]
    # 无 frame 图时不应回退 scene
    assert not item.get("frame_preview_url")
    assert not item.get("preview_fallback_url")


def test_storyboard_board_preview_fallback_video_when_no_frame():
    """无 frame 图片、有视频时：frame_preview 空，preview_fallback 为视频。"""
    from core.models.entities import (
        Project,
        Script,
        ShotSubShotVideo,
        ShotVideoClip,
        ShotVideoTrack,
        VideoPlan,
        VideoStyleMode,
    )
    from core.store.memory import MemoryStore
    from tests.support.shot_fixtures import make_shot

    store = MemoryStore()
    project = Project(title="预览兼容")
    store.add_project(project)
    script = Script(project_id=project.id, title="s", style_mode=VideoStyleMode.AI_VIDEO)
    store.add_script(script)
    video = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.VIDEO,
        name="clip.mp4",
        url="https://cdn.example.com/clip.mp4",
    )
    store.add_media_asset(video)
    shot = make_shot(order=0, duration_ms=3000, text="镜")
    sub = shot.sub_shots[0].model_copy(
        update={
            "images": [],
            "videos": [
                ShotSubShotVideo(media_id=video.id, source_kind="video", end_ms=3000),
            ],
        }
    )
    track = ShotVideoTrack(
        name="主画面",
        z_index=0,
        clips=[
            ShotVideoClip(
                start_ms=0,
                end_ms=3000,
                source_sub_shot_id=sub.id,
                media_id=video.id,
                source_kind="video",
            )
        ],
    )
    shot = shot.model_copy(update={"sub_shots": [sub], "video_tracks": [track]})
    store.set_video_plan(
        VideoPlan(script_id=script.id, mode=VideoStyleMode.AI_VIDEO, shots=[shot])
    )

    view = BoardBuilder(store).build("storyboard", project.id, script.id)
    item = view.items[0]
    assert not item.get("frame_preview_url")
    assert not item.get("frame_asset_name")
    assert item.get("preview_fallback_kind") == "video"
    assert "clip.mp4" in str(item.get("preview_fallback_url") or "") or item.get(
        "preview_fallback_url"
    )
