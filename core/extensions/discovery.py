"""通过 importlib.metadata entry_points 发现扩展。"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import Any, Callable, Iterator

from core.extensions.constants import (
    ENTRY_GROUP_MCP_SERVERS,
    ENTRY_GROUP_SKILLS,
    ENTRY_GROUP_TOOLS,
)

logger = logging.getLogger("core.extensions.discovery")


def _entry_points_for_group(group: str):
    """兼容 Python 3.11/3.12 entry_points API。"""
    eps = entry_points()
    if hasattr(eps, "select"):
        return eps.select(group=group)
    return eps.get(group, [])  # type: ignore[union-attr]


def iter_entry_points(group: str) -> Iterator[tuple[str, Any]]:
    """迭代指定分组的 (name, EntryPoint)。"""
    for ep in _entry_points_for_group(group):
        yield ep.name, ep


def load_entry_point_callable(group: str, name: str) -> Callable[..., Any] | None:
    """加载单个 entry_point 可调用对象。"""
    for ep_name, ep in iter_entry_points(group):
        if ep_name == name:
            try:
                return ep.load()
            except Exception:
                logger.exception("加载 entry_point 失败：%s.%s", group, name)
                return None
    return None


def call_all_entry_points(
    group: str,
    *,
    on_call: Callable[[str, Callable[..., Any]], None],
) -> None:
    """遍历分组内全部 entry_point 并调用回调。"""
    for name, ep in iter_entry_points(group):
        try:
            fn = ep.load()
        except Exception:
            logger.exception("加载 entry_point 失败：%s.%s", group, name)
            continue
        try:
            on_call(name, fn)
        except Exception:
            logger.exception("执行 entry_point 失败：%s.%s", group, name)


__all__ = [
    "ENTRY_GROUP_SKILLS",
    "ENTRY_GROUP_TOOLS",
    "ENTRY_GROUP_MCP_SERVERS",
    "iter_entry_points",
    "load_entry_point_callable",
    "call_all_entry_points",
]
