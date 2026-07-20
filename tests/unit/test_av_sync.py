"""音画时长协调（av_sync）单元测试。"""

from __future__ import annotations

from core.edit.av_sync import (
    apply_sync_action_to_shot,
    classify_tier,
    compute_delta_ms,
    infer_sync_policy,
    probe_shot_durations,
    rank_strategies,
    reconcile_shot_av,
    resolve_sync_policy,
)
from core.edit.av_sync.types import META_FREEZE_TAIL_MS, META_PLAYBACK_RATE, ShotDurationProbe, SyncAction
from core.models.entities import (
    MediaAsset,
    MediaAssetType,
    Shot,
    ShotAudioClip,
    ShotAudioTrack,
    ShotVideoClip,
    ShotVideoTrack,
    VideoPlan,
    VideoStyleMode,
)
from core.store.memory import MemoryStore


def _shot_with_av(
    *,
    tts_ms: int = 8000,
    video_ms: int = 5000,
    media_id_audio: str = "aud_1",
    media_id_video: str = "vid_1",
    sync_policy: str = "narration_master",
    lip_sync: bool = False,
) -> Shot:
    """构造带 voice + video 轨的测试镜头。"""
    return Shot(
        id="shot_1",
        order=0,
        duration_ms=max(tts_ms, video_ms),
        sync_policy=sync_policy,  # type: ignore[arg-type]
        lip_sync_required=lip_sync,
        audio_tracks=[
            ShotAudioTrack(
                kind="voice",
                clips=[
                    ShotAudioClip(
                        id="sac_1",
                        start_ms=0,
                        end_ms=tts_ms,
                        media_id=media_id_audio,
                        text="旁白测试文案",
                    )
                ],
            )
        ],
        video_tracks=[
            ShotVideoTrack(
                z_index=0,
                clips=[
                    ShotVideoClip(
                        id="svc_1",
                        start_ms=0,
                        end_ms=video_ms,
                        media_id=media_id_video,
                        source_kind="video",
                    )
                ],
            )
        ],
    )


def _store_with_media(shot: Shot, *, tts_ms: int, video_ms: int) -> MemoryStore:
    """写入带 duration_ms metadata 的音视频媒体。"""
    store = MemoryStore()
    plan = VideoPlan(
        script_id="scr_1",
        mode=VideoStyleMode.AI_VIDEO,
        shots=[shot],
    )
    store.set_video_plan(plan)
    store.media_assets["aud_1"] = MediaAsset(
        id="aud_1",
        project_id="p1",
        script_id="scr_1",
        type=MediaAssetType.AUDIO,
        name="tts",
        url="file://aud.mp3",
        metadata={"duration_ms": tts_ms, "shot_id": shot.id},
    )
    store.media_assets["vid_1"] = MediaAsset(
        id="vid_1",
        project_id="p1",
        script_id="scr_1",
        type=MediaAssetType.VIDEO,
        name="clip",
        url="file://vid.mp4",
        metadata={"duration_ms": video_ms, "shot_id": shot.id},
    )
    return store


def test_infer_sync_policy_storybook_default():
    """故事书模式默认配音为主。"""
    shot = Shot(id="s", sync_policy="narration_master")
    assert infer_sync_policy(shot, style_mode="storybook") == "narration_master"


def test_infer_sync_policy_lip_sync_forces_visual():
    """口型要求强制 visual_master。"""
    shot = Shot(id="s", lip_sync_required=True, sync_policy="narration_master")
    assert resolve_sync_policy(shot) == "visual_master"


def test_classify_tier_boundaries():
    """Tier 边界与 lip_sync 升级。"""
    shot = Shot(id="s")
    assert classify_tier(400, shot) == 0
    assert classify_tier(800, shot) == 1
    assert classify_tier(2500, shot) == 2
    assert classify_tier(5000, shot) == 3
    lip = Shot(id="s", lip_sync_required=True)
    assert classify_tier(900, lip) == 3


def test_compute_delta_narration_master():
    """narration_master 偏差对比视频素材而非已拉长的槽位。"""
    probe = ShotDurationProbe(shot_id="s", tts_ms=8000, video_ms=5000, slot_ms=8000)
    assert compute_delta_ms(probe, "narration_master") == 3000
    # 无视频素材、槽位已对齐 → 0
    still = ShotDurationProbe(shot_id="s", tts_ms=8000, video_ms=0, slot_ms=8000)
    assert compute_delta_ms(still, "narration_master") == 0


def test_rank_strategies_video_rate_for_small_stretch():
    """小幅配音超长优先视频慢放（NLE rate<1）。"""
    probe = ShotDurationProbe(shot_id="s", tts_ms=5500, video_ms=5000, slot_ms=5000)
    actions = rank_strategies(probe, "narration_master")
    assert actions
    top = actions[0]
    assert top.kind == "video_rate"
    assert top.auto_eligible
    rate = float(top.params["playback_rate"])
    assert rate < 1.0  # 慢放
    assert abs(rate - 5000 / 5500) < 0.01


def test_apply_video_rate_writes_metadata():
    """apply video_rate 写入 playback_rate 并扩展终点。"""
    shot = _shot_with_av(tts_ms=5500, video_ms=5000)
    action = SyncAction(
        kind="video_rate",
        params={"playback_rate": 5000 / 5500, "target_ms": 5500},
        quality_score=30,
        auto_eligible=True,
    )
    updated = apply_sync_action_to_shot(shot, action)
    clip = updated.video_tracks[0].clips[0]
    assert abs(float(clip.metadata[META_PLAYBACK_RATE]) - 5000 / 5500) < 0.01
    assert clip.end_ms == 5500
    assert updated.duration_ms == 5500


def test_apply_freeze_tail():
    """freeze_tail 写入 freeze_tail_ms。"""
    shot = _shot_with_av(tts_ms=8000, video_ms=5000)
    action = SyncAction(
        kind="freeze_tail",
        params={"freeze_tail_ms": 2250, "video_rate": 1 / 1.15, "target_ms": 8000},
        quality_score=25,
        auto_eligible=True,
    )
    updated = apply_sync_action_to_shot(shot, action)
    clip = updated.video_tracks[0].clips[0]
    assert clip.metadata[META_FREEZE_TAIL_MS] == 2250
    assert clip.end_ms == 8000


def test_reconcile_tier1_auto_applies():
    """Tier1 偏差自动应用策略。"""
    shot = _shot_with_av(tts_ms=6500, video_ms=5000)
    store = _store_with_media(shot, tts_ms=6500, video_ms=5000)
    plan = store.get_video_plan_for_script("scr_1")
    assert plan is not None
    result = reconcile_shot_av(store, shot, plan=plan, mode="hybrid")
    assert result.tier == 1
    assert result.status == "auto_applied"
    assert result.shot is not None
    assert result.shot.duration_ms >= 6500
    assert result.applied is not None


def test_reconcile_tier3_sets_need_regen():
    """大偏差进入 Agent 打回。"""
    shot = _shot_with_av(tts_ms=10000, video_ms=5000)
    store = _store_with_media(shot, tts_ms=10000, video_ms=5000)
    plan = store.get_video_plan_for_script("scr_1")
    result = reconcile_shot_av(store, shot, plan=plan, mode="hybrid")
    assert result.tier == 3
    assert result.status == "needs_agent_review"
    assert result.shot is not None
    assert result.shot.need_regen is True
    assert "tts_longer_than_video" in result.shot.regen_reason
    assert result.regen_reason is not None
    assert result.regen_reason["recommended"]


def test_probe_reads_media_duration():
    """probe 从 media metadata 读取时长。"""
    shot = _shot_with_av(tts_ms=8000, video_ms=5000)
    store = _store_with_media(shot, tts_ms=8000, video_ms=5000)
    plan = store.get_video_plan_for_script("scr_1")
    probe = probe_shot_durations(store, shot, plan=plan)
    assert probe.tts_ms == 8000
    assert probe.video_ms == 5000
