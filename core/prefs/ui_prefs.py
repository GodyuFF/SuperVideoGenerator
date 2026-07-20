"""本机 UI 偏好（界面语言等）持久化。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from core.store.project_paths import DATA_ROOT

UiLocale = Literal["zh-CN", "en"]
SUPPORTED_UI_LOCALES: tuple[str, ...] = ("zh-CN", "en")
DEFAULT_UI_LOCALE: UiLocale = "zh-CN"
PREFS_FILENAME = "ui_prefs.json"


class UiPrefsError(ValueError):
    """UI 偏好校验失败。"""


def ui_prefs_path() -> Path:
    """返回 data/ui_prefs.json 绝对路径。"""
    return DATA_ROOT / PREFS_FILENAME


def normalize_ui_locale(raw: Any) -> UiLocale:
    """校验并规范化 ui_locale；非法值抛 UiPrefsError。"""
    value = str(raw or "").strip()
    if value not in SUPPORTED_UI_LOCALES:
        raise UiPrefsError(f"不支持的 ui_locale：{value!r}，允许 {SUPPORTED_UI_LOCALES}")
    return value  # type: ignore[return-value]


def default_ui_prefs() -> dict[str, Any]:
    """默认 UI 偏好。"""
    return {"ui_locale": DEFAULT_UI_LOCALE}


def load_ui_prefs() -> dict[str, Any]:
    """读取 UI 偏好；文件缺失或损坏时回退默认。"""
    path = ui_prefs_path()
    if not path.is_file():
        return default_ui_prefs()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_ui_prefs()
    if not isinstance(raw, dict):
        return default_ui_prefs()
    try:
        locale = normalize_ui_locale(raw.get("ui_locale", DEFAULT_UI_LOCALE))
    except UiPrefsError:
        locale = DEFAULT_UI_LOCALE
    return {"ui_locale": locale}


def save_ui_prefs(prefs: dict[str, Any]) -> dict[str, Any]:
    """校验并写入 UI 偏好，返回规范化结果。"""
    locale = normalize_ui_locale(prefs.get("ui_locale", DEFAULT_UI_LOCALE))
    out = {"ui_locale": locale}
    path = ui_prefs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def patch_ui_prefs(body: dict[str, Any]) -> dict[str, Any]:
    """合并 PATCH 体到现有偏好并落盘。"""
    current = load_ui_prefs()
    if "ui_locale" in body:
        current["ui_locale"] = normalize_ui_locale(body.get("ui_locale"))
    return save_ui_prefs(current)
