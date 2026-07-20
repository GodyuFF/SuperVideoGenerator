"""主轨策略推断、偏差计算与 Tier 分级。"""

from __future__ import annotations

from core.edit.av_sync.types import (
    LIP_SYNC_TIER3_MS,
    TIER0_MAX_MS,
    TIER1_MAX_MS,
    TIER2_MAX_MS,
    ShotDurationProbe,
    SyncPolicy,
    SyncTier,
)
from core.models.entities import Shot, VideoStyleMode


def infer_sync_policy(
    shot: Shot,
    *,
    style_mode: str = "",
    has_character_dialogue: bool | None = None,
) -> SyncPolicy:
    """无显式标注时按风格与对白推断主轨策略。"""
    if shot.lip_sync_required:
        return "visual_master"
    explicit = str(shot.sync_policy or "").strip()
    # 用户/复核已写过非默认且有 sync_notes 时信任显式值；否则可再推断
    # 持久化默认均为 narration_master，需结合风格重推断
    mode = (style_mode or "").strip().lower()
    dialogue = (
        has_character_dialogue
        if has_character_dialogue is not None
        else _shot_has_dialogue(shot)
    )
    if mode in (VideoStyleMode.STORYBOOK.value, "storybook", ""):
        return "narration_master"
    if mode in (VideoStyleMode.AI_VIDEO.value, VideoStyleMode.FRAME_I2V.value, "ai_video", "frame_i2v"):
        if dialogue:
            return "balanced" if explicit != "visual_master" else "visual_master"
        return "narration_master"
    if explicit in ("narration_master", "visual_master", "balanced"):
        return explicit  # type: ignore[return-value]
    return "narration_master"


def _shot_has_dialogue(shot: Shot) -> bool:
    """镜内是否存在角色对白配音幕。"""
    for track in shot.audio_tracks:
        if track.kind != "voice":
            continue
        for clip in track.clips:
            if str(clip.character_ref or "").strip() and str(clip.text or "").strip():
                return True
    return False


def resolve_sync_policy(
    shot: Shot,
    probe: ShotDurationProbe | None = None,
) -> SyncPolicy:
    """解析最终主轨：显式合法值优先，否则推断。"""
    if shot.lip_sync_required:
        return "visual_master"
    raw = str(shot.sync_policy or "").strip()
    # 若用户在 sync_notes 中锁定，或已 patch 过非默认，保留显式值
    if raw in ("visual_master", "balanced"):
        return raw  # type: ignore[return-value]
    if raw == "narration_master" and str(shot.sync_notes or "").strip():
        return "narration_master"
    style = probe.style_mode if probe else ""
    dialogue = probe.has_character_dialogue if probe else None
    return infer_sync_policy(shot, style_mode=style, has_character_dialogue=dialogue)


def compute_delta_ms(probe: ShotDurationProbe, policy: SyncPolicy) -> int:
    """按主轨计算需补齐的正偏差（毫秒）。

    槽位常被 TTS 同步拉长至配音时长，故 narration_master 以**视频素材实测**
    为画面基准（有 video_ms 时），避免 slot≈tts 导致永远 delta=0。
    """
    t = int(probe.tts_ms or 0)
    v = int(probe.video_ms or 0)
    s = int(probe.slot_ms or 0)
    if t <= 0 and v <= 0:
        return 0
    if policy == "narration_master":
        if t <= 0:
            return 0
        # 有真视频：偏差 = 配音 - 视频素材；无视频（静图）：槽位已铺满则 0
        if v > 0:
            return max(0, t - v)
        return max(0, t - s) if s > 0 else 0
    if policy == "visual_master":
        visual = v if v > 0 else s
        return max(0, visual - t) if visual > 0 else 0
    # balanced：有符号差值 T - visual
    visual = v if v > 0 else s
    return t - visual if visual > 0 or t > 0 else 0


def classify_tier(
    delta_ms: int,
    shot: Shot,
    *,
    abs_delta: bool = True,
) -> SyncTier:
    """按偏差绝对值与 lip_sync 约束划分协调层级。"""
    d = abs(int(delta_ms)) if abs_delta else int(delta_ms)
    d = abs(d)
    if d <= TIER0_MAX_MS:
        return 0
    if shot.lip_sync_required and d > LIP_SYNC_TIER3_MS:
        return 3
    if d <= TIER1_MAX_MS:
        return 1
    if d <= TIER2_MAX_MS:
        return 2
    return 3
