"""音画时长协调（AV Sync）：按镜主轨策略分层修复配音与画面偏差。"""

from core.edit.av_sync.apply import apply_sync_action_to_shot
from core.edit.av_sync.orchestrator import (
    apply_named_sync_action,
    reconcile_script_av,
    reconcile_shot_av,
)
from core.edit.av_sync.policy import (
    classify_tier,
    compute_delta_ms,
    infer_sync_policy,
    resolve_sync_policy,
)
from core.edit.av_sync.probe import probe_shot_durations
from core.edit.av_sync.strategies import rank_strategies
from core.edit.av_sync.types import (
    META_FREEZE_TAIL_MS,
    META_PLAYBACK_RATE,
    AvSyncResult,
    ShotDurationProbe,
    SyncAction,
    SyncPolicy,
    SyncStatus,
    SyncTier,
)

__all__ = [
    "META_FREEZE_TAIL_MS",
    "META_PLAYBACK_RATE",
    "AvSyncResult",
    "ShotDurationProbe",
    "SyncAction",
    "SyncPolicy",
    "SyncStatus",
    "SyncTier",
    "apply_named_sync_action",
    "apply_sync_action_to_shot",
    "classify_tier",
    "compute_delta_ms",
    "infer_sync_policy",
    "probe_shot_durations",
    "rank_strategies",
    "reconcile_script_av",
    "reconcile_shot_av",
    "resolve_sync_policy",
]
