"""交互日志维护：启动 retention 与手动 prune。"""

from __future__ import annotations

import logging
from typing import Sequence

from core.interaction_log.store import InteractionLogStore

logger = logging.getLogger("core.interaction_log.maintenance")

DEFAULT_STARTUP_RETENTION_DAYS = 30
DEFAULT_STARTUP_KINDS = ("api_request",)


def run_startup_retention(
    store: InteractionLogStore,
    *,
    days: int = DEFAULT_STARTUP_RETENTION_DAYS,
    kinds: Sequence[str] = DEFAULT_STARTUP_KINDS,
) -> int:
    """启动时删除过期的低价值 api_request 等记录。"""
    deleted = store.delete_older_than(days, kinds=kinds)
    if deleted:
        logger.info(
            "交互日志 retention：删除 %s 条（>%s 天，kinds=%s）",
            deleted,
            days,
            list(kinds),
        )
    return deleted


def prune_and_vacuum(
    store: InteractionLogStore,
    *,
    days: int,
    kinds: Sequence[str],
    vacuum: bool = False,
) -> dict[str, int | bool]:
    """按天数与 kind 清理，可选 VACUUM。"""
    size_before = store.db_path.stat().st_size if store.db_path.is_file() else 0
    deleted = store.delete_older_than(days, kinds=kinds)
    if vacuum:
        store.vacuum()
    size_after = store.db_path.stat().st_size if store.db_path.is_file() else 0
    return {
        "deleted": deleted,
        "vacuum": vacuum,
        "size_before_bytes": size_before,
        "size_after_bytes": size_after,
    }
