"""视频位置确定性编译与重投影行为测试（新模型）。"""

from core.edit.shot_detail_sync import _bind_tts_to_plan
from core.edit.timeline import (
    compile_timeline_from_shots,
    merge_timeline_with_fallback,
    realign_edit_timeline_durations_from_plan,
    realign_edit_timeline_from_plan,
)
from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.editing.opencut_handler import handle_add_clip
from core.models.entities import MediaAsset, MediaAssetType
from tests.support.shot_fixtures import _store_with_two_shots


def _add_tts(store, script_id: str, shot, duration_ms: int) -> MediaAsset:
    """为指定镜头挂一条带 metadata 时长的 TTS 音频资产。"""
    media = MediaAsset(
        project_id=list(store.projects.keys())[0],
        script_id=script_id,
        type=MediaAssetType.AUDIO,
        name=f"配音{shot.order}",
        url=f"https://audio.test/{shot.id}.mp3",
        metadata={"shot_id": shot.id, "duration_ms": duration_ms},
    )
    store.add_media_asset(media)
    return media


def _main_clips(timeline):
    """按起点排序返回主视频层 clips。"""
    layer = next(l for l in timeline.video_layers if l.z_index == 0)
    return sorted(layer.clips, key=lambda c: c.start_ms)


def test_compile_timeline_positions_shots_sequentially():
    """compile_timeline_from_shots 应按镜顺序累加偏移。"""
    store, script_id, shot1, shot2 = _store_with_two_shots()
    plan = store.get_video_plan_for_script(script_id)
    timeline = compile_timeline_from_shots(store, script_id=script_id, plan=plan)
    clips = _main_clips(timeline)
    by_shot = {str((c.metadata or {}).get("shot_id") or c.source_refs.shot_id): c for c in clips}
    assert by_shot[shot1.id].start_ms == 0
    assert by_shot[shot1.id].end_ms == 3000
    assert by_shot[shot2.id].start_ms == 3000
    assert by_shot[shot2.id].end_ms == 7000


def test_merge_keeps_agent_clip_positions():
    """LLM 提供的带 shot 引用 clip 保留给定位置（由 compile 路径负责确定性投影）。"""
    store, script_id, shot1, shot2 = _store_with_two_shots()
    plan = store.get_video_plan_for_script(script_id)
    llm_tracks = {
        "video": [
            {
                "id": "llm_clip_1",
                "start_ms": 5000,
                "end_ms": 8000,
                "label": "镜一",
                "metadata": {"shot_id": shot1.id, "order": 0},
            },
        ]
    }
    timeline = merge_timeline_with_fallback(
        store, script_id=script_id, plan=plan, llm_tracks=llm_tracks
    )
    clips = _main_clips(timeline)
    llm_clip = next(c for c in clips if c.id == "llm_clip_1")
    assert llm_clip.start_ms == 5000


def test_realign_reprojects_when_not_user_edited():
    """非 user_edited 时间轴在镜时长变更后应重新投影。"""
    store, script_id, shot1, shot2 = _store_with_two_shots()
    plan = store.get_video_plan_for_script(script_id)
    timeline = compile_timeline_from_shots(store, script_id=script_id, plan=plan)
    store.set_edit_timeline(timeline)
    _add_tts(store, script_id, shot1, 5000)
    from core.edit.shot_detail_sync import sync_plan_from_tts

    sync_plan_from_tts(store, script_id)
    assert realign_edit_timeline_from_plan(store, script_id) is True
    aligned = store.get_edit_timeline_for_script(script_id)
    clips = _main_clips(aligned)
    assert clips[0].end_ms - clips[0].start_ms == 5000


def test_realign_skips_user_edited_timeline():
    """user_edited 时间轴不应被系统重投影覆盖。"""
    store, script_id, shot1, shot2 = _store_with_two_shots()
    plan = store.get_video_plan_for_script(script_id)
    timeline = compile_timeline_from_shots(store, script_id=script_id, plan=plan)
    layer = timeline.video_layers[0]
    edited = [
        layer.clips[0],
        layer.clips[1].model_copy(update={"start_ms": 4000, "end_ms": 8000}),
    ]
    store.set_edit_timeline(
        timeline.model_copy(
            update={
                "user_edited": True,
                "video_layers": [layer.model_copy(update={"clips": edited})],
            }
        )
    )
    _add_tts(store, script_id, shot1, 5000)
    assert realign_edit_timeline_durations_from_plan(store, script_id) is False
    unchanged = store.get_edit_timeline_for_script(script_id)
    clips = _main_clips(unchanged)
    assert clips[1].start_ms == 4000


def test_add_clip_appends_audio_with_media_duration():
    store, script_id, shot1, shot2 = _store_with_two_shots()
    plan = store.get_video_plan_for_script(script_id)
    timeline = compile_timeline_from_shots(store, script_id=script_id, plan=plan)
    store.set_edit_timeline(timeline)
    existing_audio_count = len(timeline.tracks.get("audio", []))

    bgm = MediaAsset(
        project_id=list(store.projects.keys())[0],
        script_id=script_id,
        type=MediaAssetType.AUDIO,
        name="背景音乐",
        url="https://audio.test/bgm.mp3",
        metadata={"duration_ms": 12000},
    )
    store.add_media_asset(bgm)

    ctx = AgentRunContext(
        task_brief="加背景音乐",
        work_context={"project_id": list(store.projects.keys())[0], "script_id": script_id},
        script_id=script_id,
        step_id="step1",
        agent_name="editing_agent",
    )
    result = handle_add_clip(
        store, ctx, {"media_id": bgm.id, "track": "audio", "start_ms": 500}
    )
    assert result.ok

    updated = store.get_edit_timeline_for_script(script_id)
    audio_clips = updated.tracks.get("audio", [])
    assert len(audio_clips) == existing_audio_count + 1
    added = next(c for c in audio_clips if c.asset_ref == bgm.id)
    assert added.start_ms == 500
    assert added.end_ms == 500 + 12000


def test_bind_tts_probe_failures():
    store, script_id, shot1, shot2 = _store_with_two_shots()
    media = MediaAsset(
        project_id=list(store.projects.keys())[0],
        script_id=script_id,
        type=MediaAssetType.AUDIO,
        name="坏音频",
        url="https://audio.test/broken.mp3",
        metadata={"shot_id": shot1.id},
    )
    store.add_media_asset(media)
    _, _, probe_failures = _bind_tts_to_plan(store, script_id)
    assert len(probe_failures) == 1
    assert probe_failures[0]["shot_id"] == shot1.id


def test_edit_session_payload_from_compiled_timeline():
    """无 EditTimeline 时应从镜内结构编译多轨载荷。"""
    from apps.api.routes.edit_session import _build_timeline_payload

    store, script_id, shot1, shot2 = _store_with_two_shots()
    payload = _build_timeline_payload(store, script_id)
    assert payload is not None
    assert payload["source"] == "edit_timeline"
    assert payload["duration_ms"] >= 7000
