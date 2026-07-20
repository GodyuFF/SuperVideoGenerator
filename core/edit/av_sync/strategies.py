"""按主轨策略生成并排序音画协调候选方案。"""

from __future__ import annotations

from core.edit.av_sync.types import (
    AUDIO_RATE_MAX,
    AUDIO_RATE_MIN,
    FREEZE_TAIL_AUTO_MAX_MS,
    VIDEO_RATE_AUTO_MAX,
    VIDEO_RATE_COMBINED_MAX,
    ShotDurationProbe,
    SyncAction,
    SyncPolicy,
)


def rank_strategies(
    probe: ShotDurationProbe,
    policy: SyncPolicy,
    *,
    lip_sync_required: bool = False,
) -> list[SyncAction]:
    """生成可行策略并按 quality_score 降序排序。"""
    actions: list[SyncAction] = []
    t = int(probe.tts_ms or 0)
    v = int(probe.video_ms or 0)
    visual = int(probe.visual_ms or 0)

    if policy == "narration_master" and t > 0 and v > 0 and t > v:
        actions.extend(_narration_longer_actions(t, v, lip_sync_required=lip_sync_required))
    elif policy == "narration_master" and t > 0 and v <= 0 and t > visual:
        # 无视频素材（故事书静图）：只需扩展槽位
        actions.append(
            SyncAction(
                kind="extend_video_slot",
                params={"target_ms": t},
                quality_score=40.0,
                auto_eligible=True,
                label="扩展镜槽位至配音时长",
                description=f"将画面槽位从 {visual}ms 扩展到配音 {t}ms（静图可 loop）",
            )
        )
    elif policy == "visual_master" and v > 0 and t > 0 and v > t:
        actions.extend(_visual_longer_actions(t, v, lip_sync_required=lip_sync_required))
    elif policy == "balanced" and t > 0 and visual > 0:
        diff = t - visual
        if abs(diff) > 500:
            if diff > 0 and v > 0:
                actions.extend(
                    _narration_longer_actions(t, v, lip_sync_required=lip_sync_required)
                )
            elif diff < 0 and v > 0:
                actions.extend(
                    _visual_longer_actions(t, v, lip_sync_required=lip_sync_required)
                )

    # 结构级兜底（Tier2/3）
    if t > 0 and (v > 0 or visual > 0) and abs(t - max(v, visual)) > 500:
        actions.append(
            SyncAction(
                kind="split_shot",
                params={"reason": "tts_video_mismatch"},
                quality_score=10.0,
                auto_eligible=False,
                label="拆镜",
                description="将过长配音拆成两镜，各自匹配画面",
            )
        )
        if policy != "visual_master" or not lip_sync_required:
            actions.append(
                SyncAction(
                    kind="extend_video_gen",
                    params={"target_ms": t, "current_video_ms": v},
                    quality_score=8.0,
                    auto_eligible=False,
                    label="补生成视频",
                    description="再生成一段衔接视频以铺满配音时长",
                )
            )
        actions.append(
            SyncAction(
                kind="rewrite_narration",
                params={"target_ms": v or visual},
                quality_score=5.0,
                auto_eligible=False,
                label="改写配音文案",
                description="缩短或改写旁白后重新配音以匹配画面",
            )
        )
        actions.append(
            SyncAction(
                kind="regen_shot",
                params={},
                quality_score=1.0,
                auto_eligible=False,
                label="整镜重生成",
                description="打回 video_agent / tts_agent 整镜重生",
            )
        )

    actions.sort(key=lambda a: a.quality_score, reverse=True)
    return actions


def _narration_longer_actions(
    tts_ms: int,
    video_ms: int,
    *,
    lip_sync_required: bool,
) -> list[SyncAction]:
    """配音长于视频时的机械与结构策略。

    playback_rate 采用 NLE 语义：rate<1 慢放（时长变长），rate>1 加速。
    慢放填满时 rate = video_ms / tts_ms。
    """
    actions: list[SyncAction] = []
    stretch = tts_ms / max(video_ms, 1)  # 时长拉伸比 >1
    delta = tts_ms - video_ms
    nle_rate = video_ms / max(tts_ms, 1)  # <1 慢放

    if stretch <= VIDEO_RATE_AUTO_MAX:
        score = 30.0
        if 0.9 <= stretch <= 1.1:
            score += 5.0
        actions.append(
            SyncAction(
                kind="video_rate",
                params={"playback_rate": round(nle_rate, 4), "target_ms": tts_ms},
                quality_score=score,
                auto_eligible=True,
                label=f"视频慢放 {stretch:.2f}x 时长",
                description=f"将 {video_ms}ms 视频慢放到配音 {tts_ms}ms（rate={nle_rate:.2f}），保留自然语速",
            )
        )
    elif stretch <= VIDEO_RATE_COMBINED_MAX and not lip_sync_required:
        # 视频最多慢放到 stretch=1.15 → nle_rate = 1/1.15
        max_stretch = VIDEO_RATE_AUTO_MAX
        video_nle = 1.0 / max_stretch
        stretched = int(video_ms * max_stretch)
        # 配音加速：缩短配音到 stretched
        audio_rate = tts_ms / max(stretched, 1)  # >1 加速
        audio_rate = max(AUDIO_RATE_MIN, min(AUDIO_RATE_MAX, audio_rate))
        actions.append(
            SyncAction(
                kind="combined_rate",
                params={
                    "video_rate": round(video_nle, 4),
                    "audio_rate": round(audio_rate, 4),
                    "target_ms": stretched,
                },
                quality_score=22.0,
                auto_eligible=True,
                label=f"双向变速 视频×{max_stretch:.2f} + 配音{audio_rate:.2f}x",
                description="画面与配音各承担一部分时长差，避免单边过度变速",
            )
        )

    freeze_ms = 0
    if stretch > VIDEO_RATE_AUTO_MAX:
        stretched = int(video_ms * VIDEO_RATE_AUTO_MAX)
        freeze_ms = max(0, tts_ms - stretched)
        if freeze_ms > 0:
            auto = freeze_ms <= FREEZE_TAIL_AUTO_MAX_MS
            score = 25.0 if auto else -5.0
            if freeze_ms > FREEZE_TAIL_AUTO_MAX_MS:
                score -= 30.0
            actions.append(
                SyncAction(
                    kind="freeze_tail",
                    params={
                        "freeze_tail_ms": freeze_ms,
                        "video_rate": round(1.0 / VIDEO_RATE_AUTO_MAX, 4),
                        "target_ms": tts_ms,
                    },
                    quality_score=score,
                    auto_eligible=auto and not lip_sync_required,
                    label=f"尾帧定格 {freeze_ms}ms",
                    description="视频慢放至上限后再定格最后一帧以铺满配音",
                )
            )

    actions.append(
        SyncAction(
            kind="extend_video_slot",
            params={"target_ms": tts_ms},
            quality_score=15.0,
            auto_eligible=stretch <= VIDEO_RATE_AUTO_MAX
            or freeze_ms <= FREEZE_TAIL_AUTO_MAX_MS,
            label="扩展视频槽位",
            description="将镜内视频轨终点拉到配音时长（配合 rate/freeze 导出）",
        )
    )
    del delta
    return actions


def _visual_longer_actions(
    tts_ms: int,
    video_ms: int,
    *,
    lip_sync_required: bool,
) -> list[SyncAction]:
    """画面长于配音时的策略。"""
    actions: list[SyncAction] = []
    # 放慢配音铺满画面：NLE rate = tts/video < 1
    needed_rate = tts_ms / max(video_ms, 1)
    if AUDIO_RATE_MIN <= needed_rate <= AUDIO_RATE_MAX and not lip_sync_required:
        actions.append(
            SyncAction(
                kind="audio_rate",
                params={"playback_rate": round(needed_rate, 4), "target_ms": video_ms},
                quality_score=20.0 if needed_rate >= 0.9 else 12.0,
                auto_eligible=True,
                label=f"配音慢放 {needed_rate:.2f}x",
                description=f"将配音从 {tts_ms}ms 拉长至画面 {video_ms}ms",
            )
        )
    actions.append(
        SyncAction(
            kind="extend_video_slot",
            params={"target_ms": tts_ms, "trim_video": True},
            quality_score=18.0,
            auto_eligible=True,
            label="裁短画面至配音",
            description=f"将视频槽位从 {video_ms}ms 裁到配音 {tts_ms}ms",
        )
    )
    return actions
