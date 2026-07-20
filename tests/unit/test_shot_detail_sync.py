"""分镜详设同步与 patch 落盘测试（新模型：镜内多轨 Shot）。"""

from core.edit.shot_detail_sync import (
    _bind_tts_to_plan,
    _normalize_cumulative_sub_shots,
    apply_shot_detail_patches,
    backfill_plan_subtitles_from_voice,
    is_shot_detail_complete,
    lazy_sync_storyboard_if_needed,
    refresh_shot_tts_durations_if_drifted,
    resolve_effective_camera_motion,
    sync_plan_from_tts,
)
from core.edit.shot_query import build_shot_details_query
from core.models.entities import (
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    Shot,
    ShotAudioClip,
    ShotAudioTrack,
    ShotSubShot,
    ShotVideoClip,
    ShotVideoTrack,
    VideoPlan,
    VideoStyleMode,
)
from core.store.memory import MemoryStore
from tests.support.frame_fixtures import ensure_shot_frame_image
from tests.support.shot_fixtures import make_shot


def _base_store() -> tuple[MemoryStore, str, object]:
    store = MemoryStore()
    project = Project(title="详设测试")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1", duration_sec=30, content_md="# 测试")
    store.add_script(script)
    shot = make_shot(order=0, duration_ms=3000, text="这是一段旁白")
    ensure_shot_frame_image(
        store,
        project_id=project.id,
        script_id=script.id,
        shot=shot,
        image_url="https://images.test/frame.png",
    )
    plan = VideoPlan(script_id=script.id, mode=VideoStyleMode.STORYBOOK, shots=[shot])
    store.set_video_plan(plan)
    audio = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.AUDIO,
        name="旁白",
        url="https://audio.test/narration.mp3",
        metadata={
            "shot_id": shot.id,
            "duration_ms": 5200,
            "subtitle_cues": [
                {"text": "这是一段", "start_ms": 0, "end_ms": 2000},
                {"text": "旁白", "start_ms": 2000, "end_ms": 5200},
            ],
        },
    )
    store.add_media_asset(audio)
    return store, script.id, shot


def test_sync_plan_from_tts_updates_duration_and_subtitles():
    """TTS 同步应绑定 voice clip、扩展镜时长并回填字幕。"""
    store, script_id, shot = _base_store()
    result = sync_plan_from_tts(store, script_id)
    plan = store.get_video_plan_for_script(script_id)
    assert plan
    updated = plan.shots[0]
    assert updated.duration_ms == 5200
    voice = updated.audio_tracks[0].clips[0]
    assert voice.media_id
    assert voice.end_ms - voice.start_ms == 5200
    assert len(updated.subtitles) >= 1
    assert result["synced_shot_count"] >= 0


def test_normalize_cumulative_sub_shots_partitions_without_overlap():
    """TTS 同步后子镜应保持累加分段，而非全部拉满至镜终点。"""
    from core.models.entities import ShotSubShot

    subs = [
        ShotSubShot(id="a", start_ms=0, end_ms=8000, description="A"),
        ShotSubShot(id="b", start_ms=3500, end_ms=8000, description="B"),
    ]
    out = _normalize_cumulative_sub_shots(subs, 8000)
    assert out[0].start_ms == 0
    assert out[0].end_ms == 3500
    assert out[1].start_ms == 3500
    assert out[1].end_ms == 8000


def test_normalize_cumulative_sub_shots_clamps_stale_image_timings():
    """镜长压缩后，设计态 8s 画面时段应钳进缩短后的子镜区间。"""
    from core.edit.shot_validate import validate_shot_structure
    from core.edit.sub_shot_produce import validate_sub_shot_image_timings
    from core.models.entities import ShotSubShot, ShotSubShotImage

    subs = [
        ShotSubShot(
            id="a",
            start_ms=0,
            end_ms=8000,
            description="A",
            images=[ShotSubShotImage(start_ms=0, end_ms=8000)],
        ),
        ShotSubShot(
            id="b",
            start_ms=8000,
            end_ms=15000,
            description="B",
            images=[ShotSubShotImage(start_ms=8000, end_ms=15000)],
        ),
    ]
    out = _normalize_cumulative_sub_shots(subs, 4581)
    assert out[0].start_ms == 0
    assert out[0].end_ms == out[1].start_ms
    assert out[0].images[0].start_ms == out[0].start_ms
    assert out[0].images[0].end_ms == out[0].end_ms
    assert out[1].images[0].start_ms == out[1].start_ms
    assert out[1].images[0].end_ms == out[1].end_ms
    assert validate_sub_shot_image_timings(out[0]) == []
    assert validate_sub_shot_image_timings(out[1]) == []
    shot = Shot(
        id="shot_x",
        order=0,
        duration_ms=4581,
        sub_shots=out,
    )
    assert validate_shot_structure(shot) == []


def test_sync_plan_from_tts_preserves_cumulative_sub_shots():
    """多子镜镜位 TTS 绑定时，子镜区间按 start_ms 累加、末段对齐镜长。"""
    store, script_id, shot = _base_store()
    plan = store.get_video_plan_for_script(script_id)
    assert plan
    shot = plan.shots[0].model_copy(
        update={
            "sub_shots": [
                ShotSubShot(id="ss1", start_ms=0, end_ms=3000, description="子镜A"),
                ShotSubShot(id="ss2", start_ms=3000, end_ms=3000, description="子镜B"),
            ]
        }
    )
    plan = plan.model_copy(update={"shots": [shot]})
    store.set_video_plan(plan)

    sync_plan_from_tts(store, script_id)
    updated = store.get_video_plan_for_script(script_id).shots[0]
    assert updated.duration_ms == 5200
    assert len(updated.sub_shots) == 2
    assert updated.sub_shots[0].start_ms == 0
    assert updated.sub_shots[0].end_ms == 3000
    assert updated.sub_shots[1].start_ms == 3000
    assert updated.sub_shots[1].end_ms == 5200


def test_normalize_plan_sub_shot_ranges_repairs_overlap():
    """懒同步应修复已落盘的重叠子镜区间。"""
    from core.edit.shot_detail_sync import normalize_plan_sub_shot_ranges

    store, script_id, shot = _base_store()
    plan = store.get_video_plan_for_script(script_id)
    shot = plan.shots[0].model_copy(
        update={
            "duration_ms": 8000,
            "sub_shots": [
                ShotSubShot(id="ss1", start_ms=0, end_ms=8000, description="A"),
                ShotSubShot(id="ss2", start_ms=3500, end_ms=8000, description="B"),
            ],
        }
    )
    store.set_video_plan(plan.model_copy(update={"shots": [shot]}))
    assert normalize_plan_sub_shot_ranges(store, script_id)
    fixed = store.get_video_plan_for_script(script_id).shots[0]
    assert fixed.sub_shots[0].end_ms == 3500
    assert fixed.sub_shots[1].start_ms == 3500
    assert fixed.sub_shots[1].end_ms == 8000


def test_apply_shot_detail_patches_bumps_revision():
    store, script_id, shot = _base_store()
    sync_plan_from_tts(store, script_id)
    plan = apply_shot_detail_patches(
        store,
        script_id,
        [
            {
                "shot_id": shot.id,
                "display_instructions": "Ken Burns 缓慢推近主体",
                "camera_motion_refined": "ken_burns_in",
                "need_regen": True,
                "regen_reason": "构图需特写",
            }
        ],
    )
    assert plan.detail_revision == 1
    assert plan.shots[0].sub_shots[0].camera_motion == "ken_burns_in"
    assert plan.shots[0].need_regen is True


def test_is_shot_detail_complete_requires_media():
    store, script_id, shot = _base_store()
    assert is_shot_detail_complete(store, script_id) is False
    sync_plan_from_tts(store, script_id)
    apply_shot_detail_patches(
        store,
        script_id,
        [{"shot_id": shot.id, "display_instructions": "静态展示"}],
    )
    # 有 frame 图 + TTS 绑定后应满足 render ready
    assert is_shot_detail_complete(store, script_id) is True


def test_resolve_effective_camera_motion():
    from core.models.entities import Shot, ShotSubShot

    shot = Shot(
        sub_shots=[ShotSubShot(camera_motion="static")],
        video_tracks=[
            ShotVideoTrack(
                clips=[ShotVideoClip(camera_motion="pan_left")]
            )
        ],
    )
    assert resolve_effective_camera_motion(shot) == "static"


def test_refresh_shot_tts_durations_if_drifted_fixes_cached_value(tmp_path, monkeypatch):
    """metadata 错误且文件实测正确时，刷新应修正镜内 voice clip 时长。"""
    import wave

    from core.store import project_paths

    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path)
    store, script_id, shot = _base_store()
    project_id = store.get_script(script_id).project_id
    media_dir = tmp_path / project_id / "scripts" / script_id / "assets" / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    wav_path = media_dir / "tts.wav"
    with wave.open(str(wav_path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44100)
        handle.writeframes(b"\x00\x00" * int(44100 * 16))

    rel = f"projects/{project_id}/scripts/{script_id}/assets/media/tts.wav"
    audio = MediaAsset(
        project_id=project_id,
        script_id=script_id,
        type=MediaAssetType.AUDIO,
        name="旁白",
        url=rel,
        metadata={
            "shot_id": shot.id,
            "duration_ms": 18000,
            "subtitle_cues": [
                {"text": "这是一段", "start_ms": 0, "end_ms": 2000},
                {"text": "旁白", "start_ms": 2000, "end_ms": 5200},
            ],
        },
    )
    store.media_assets.clear()
    store.add_media_asset(audio)

    monkeypatch.setattr(
        "core.media.duration_probe.probe_media_duration_ms",
        lambda file_path, media_type: 18000,
    )
    sync_plan_from_tts(store, script_id)
    plan = store.get_video_plan_for_script(script_id)
    assert plan.shots[0].audio_tracks[0].clips[0].end_ms == 18000

    monkeypatch.setattr(
        "core.media.duration_probe.probe_media_duration_ms",
        lambda file_path, media_type: 16000,
    )
    refreshed, diffs = refresh_shot_tts_durations_if_drifted(store, script_id)
    assert refreshed is True
    plan = store.get_video_plan_for_script(script_id)
    assert plan.shots[0].audio_tracks[0].clips[0].end_ms == 16000
    assert diffs


def test_refresh_converges_when_voice_clip_has_nonzero_start(monkeypatch):
    """voice clip start_ms≠0 时刷新须收敛，避免每次 GET 无限重绑。

    复现：OpenCut 回写把镜内相对起点写成非零后，`_sync_shot_bound_voice_clips`
    把绝对终点再当时长叠加，导致 end-start 与 TTS 实测永远偏差 >200ms。
    """
    store, script_id, shot = _base_store()
    plan = store.get_video_plan_for_script(script_id)
    assert plan
    media = next(iter(store.media_assets.values()))
    tts_ms = 6340
    media.metadata = {
        **(media.metadata or {}),
        "shot_id": shot.id,
        "duration_ms": tts_ms,
    }
    # 错误的非零起点 + 偏长缓存（与 script_5b7a0126ab86 同类数据）
    bad_voice = ShotAudioTrack(
        id="sat_voice",
        name="角色音",
        kind="voice",
        clips=[
            ShotAudioClip(
                id="a_3",
                start_ms=2810,
                end_ms=11960,
                media_id=media.id,
                text="旁白",
                metadata={"edited_by": "user"},
            )
        ],
    )
    corrupted = plan.shots[0].model_copy(
        update={
            "duration_ms": 9150,
            "audio_tracks": [bad_voice],
            "subtitles": plan.shots[0].subtitles,
        }
    )
    store.set_video_plan(plan.model_copy(update={"shots": [corrupted]}))

    monkeypatch.setattr(
        "core.edit.timeline._effective_audio_media_duration_ms",
        lambda store, media, **kwargs: tts_ms,
    )

    first, _ = refresh_shot_tts_durations_if_drifted(store, script_id)
    assert first is True
    updated = store.get_video_plan_for_script(script_id).shots[0]
    voice = updated.audio_tracks[0].clips[0]
    assert voice.start_ms == 0
    assert voice.end_ms - voice.start_ms == tts_ms
    assert updated.duration_ms == tts_ms

    second, _ = refresh_shot_tts_durations_if_drifted(store, script_id)
    assert second is False


def test_bind_tts_probe_failures():
    """TTS 存在但时长探测为 0 时记入 probe_failures。"""
    store, script_id, shot = _base_store()
    store.media_assets.clear()
    media = MediaAsset(
        project_id=list(store.projects.keys())[0],
        script_id=script_id,
        type=MediaAssetType.AUDIO,
        name="坏音频",
        url="https://audio.test/broken.mp3",
        metadata={"shot_id": shot.id},
    )
    store.add_media_asset(media)
    _, _, probe_failures = _bind_tts_to_plan(store, script_id)
    assert len(probe_failures) == 1
    assert probe_failures[0]["shot_id"] == shot.id


def test_build_shot_details_query():
    store, script_id, shot = _base_store()
    sync_plan_from_tts(store, script_id)
    ctx = build_shot_details_query(store, script_id)
    assert ctx["shot_count"] == 1
    assert ctx["shots"][0]["id"] == shot.id


def test_backfill_subtitles_when_voice_media_already_bound():
    """配音已绑定 media 但镜内 subtitles 为空时应懒回填。"""
    store, script_id, shot = _base_store()
    media = MediaAsset(
        project_id=list(store.projects.keys())[0],
        script_id=script_id,
        type=MediaAssetType.AUDIO,
        name="旁白",
        url="https://audio.test/narration.mp3",
        metadata={
            "shot_id": shot.id,
            "duration_ms": 3200,
            "subtitle_cues": [
                {"text": "这是一段旁白", "start_ms": 0, "end_ms": 3200},
            ],
        },
    )
    store.add_media_asset(media)
    bound_shot = shot.model_copy(
        update={
            "subtitles": [],
            "audio_tracks": [
                ShotAudioTrack(
                    kind="voice",
                    clips=[
                        ShotAudioClip(
                            start_ms=0,
                            end_ms=3200,
                            text="这是一段旁白",
                            media_id=media.id,
                        )
                    ],
                )
            ],
        }
    )
    plan = store.get_video_plan_for_script(script_id)
    store.set_video_plan(plan.model_copy(update={"shots": [bound_shot]}))

    changed, filled = backfill_plan_subtitles_from_voice(store, script_id)
    assert changed is True
    assert filled == 1
    updated = store.get_video_plan_for_script(script_id)
    assert len(updated.shots[0].subtitles) >= 1
    assert "旁白" in updated.shots[0].subtitles[0].text

    # 懒同步入口也应触发回填
    store.set_video_plan(plan.model_copy(update={"shots": [bound_shot]}))
    assert lazy_sync_storyboard_if_needed(store, script_id) is True
    assert store.get_video_plan_for_script(script_id).shots[0].subtitles
