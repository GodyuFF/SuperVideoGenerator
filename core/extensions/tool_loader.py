"""加载 svg.tools entry_points 并注册到 ToolRegistry。"""

from __future__ import annotations

import importlib
import logging

from core.extensions.discovery import call_all_entry_points
from core.extensions.constants import ENTRY_GROUP_TOOLS
from core.llm.tools.registry import ToolRegistry

logger = logging.getLogger("core.extensions.tool_loader")

# 仓库内置扩展（未 pip install -e 时 entry_points 可能不可见，故显式加载）
_BUILTIN_TOOL_REGISTRARS: tuple[str, ...] = (
    "core.extensions.builtin.web_search:register_tools",
)


def _load_callable(target: str):
    """解析 module:attr 并返回可调用对象。"""
    module_name, attr = target.split(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, attr)


def load_extension_tools(registry: ToolRegistry) -> None:
    """调用内置扩展与 svg.tools entry_points 注册器。"""
    seen: set[str] = set()

    for target in _BUILTIN_TOOL_REGISTRARS:
        if target in seen:
            continue
        seen.add(target)
        try:
            registrar = _load_callable(target)
            registrar(registry)
        except Exception:
            logger.exception("加载内置扩展 tools 失败：%s", target)

    def _register(name: str, registrar) -> None:
        logger.debug("注册扩展 tools：%s", name)
        registrar(registry)

    call_all_entry_points(ENTRY_GROUP_TOOLS, on_call=_register)
