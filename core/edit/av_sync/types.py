"""音画协调类型、阈值与元数据键约定。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SyncPolicy = Literal["narration_master", "visual_master", "balanced"]
SyncStatus = Literal["ok", "auto_applied", "needs_user_choice", "needs_agent_review"]
SyncTier = Literal[0, 1, 2, 3]
SyncActionKind = Literal[
    "video_rate",
    "audio_rate",
    "combined_rate",
    "freeze_tail",
    "extend_video_slot",
    "split_shot",
    "extend_video_gen",
    "rewrite_narration",
    "regen_shot",
]

# 与 timeline_analysis.DURATION_MISMATCH_THRESHOLD_MS 对齐
TIER0_MAX_MS = 500
TIER1_MAX_MS = 2000
TIER2_MAX_MS = 4000
# lip_sync 时超过此偏差直接升 Tier3
LIP_SYNC_TIER3_MS = 800

# 人类可接受变速域
VIDEO_RATE_AUTO_MAX = 1.15
VIDEO_RATE_COMBINED_MAX = 1.30
AUDIO_RATE_MIN = 0.85
AUDIO_RATE_MAX = 1.15
VIDEO_RATE_HARD_MIN = 0.5
VIDEO_RATE_HARD_MAX = 2.0

# 尾帧 freeze 自动上限
FREEZE_TAIL_AUTO_MAX_MS = 2000

# clip.metadata 键
META_PLAYBACK_RATE = "playback_rate"
META_FREEZE_TAIL_MS = "freeze_tail_ms"


@dataclass
class ShotDurationProbe:
    """单镜四维时长探测结果。"""

    shot_id: str
    tts_ms: int = 0
    video_ms: int = 0
    slot_ms: int = 0
    has_character_dialogue: bool = False
    style_mode: str = ""

    @property
    def visual_ms(self) -> int:
        """画面可用时长：视频实测与槽位取较大者。"""
        return max(self.video_ms, self.slot_ms)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 API / Tool 载荷。"""
        return {
            "shot_id": self.shot_id,
            "tts_ms": self.tts_ms,
            "video_ms": self.video_ms,
            "slot_ms": self.slot_ms,
            "visual_ms": self.visual_ms,
            "has_character_dialogue": self.has_character_dialogue,
            "style_mode": self.style_mode,
        }


@dataclass
class SyncAction:
    """一条音画协调策略及其评分。"""

    kind: SyncActionKind
    params: dict[str, Any] = field(default_factory=dict)
    quality_score: float = 0.0
    auto_eligible: bool = False
    label: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """序列化为前端可选方案卡片。"""
        return {
            "kind": self.kind,
            "params": dict(self.params),
            "quality_score": self.quality_score,
            "auto_eligible": self.auto_eligible,
            "label": self.label,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> SyncAction:
        """从字典还原策略（Tier2 一键应用）。"""
        return cls(
            kind=str(raw.get("kind") or "regen_shot"),  # type: ignore[arg-type]
            params=dict(raw.get("params") or {}),
            quality_score=float(raw.get("quality_score") or 0),
            auto_eligible=bool(raw.get("auto_eligible")),
            label=str(raw.get("label") or ""),
            description=str(raw.get("description") or ""),
        )


@dataclass
class AvSyncResult:
    """单镜音画协调编排结果。"""

    shot_id: str
    status: SyncStatus
    tier: SyncTier
    policy: SyncPolicy
    delta_ms: int
    probe: ShotDurationProbe
    applied: SyncAction | None = None
    options: list[SyncAction] = field(default_factory=list)
    regen_reason: dict[str, Any] | None = None
    shot: Any = None  # 更新后的 Shot（若有）

    def to_dict(self) -> dict[str, Any]:
        """序列化为 API / Agent 观察载荷。"""
        return {
            "shot_id": self.shot_id,
            "status": self.status,
            "tier": self.tier,
            "policy": self.policy,
            "delta_ms": self.delta_ms,
            "probe": self.probe.to_dict(),
            "applied": self.applied.to_dict() if self.applied else None,
            "options": [o.to_dict() for o in self.options],
            "regen_reason": self.regen_reason,
            "proposed_sync_actions": [o.to_dict() for o in self.options],
        }
