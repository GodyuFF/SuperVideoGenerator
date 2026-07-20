"""本机偏好包：UI 语言等跨壳单源配置。"""

from core.prefs.ui_prefs import (
    DEFAULT_UI_LOCALE,
    SUPPORTED_UI_LOCALES,
    UiPrefsError,
    load_ui_prefs,
    patch_ui_prefs,
    save_ui_prefs,
)

__all__ = [
    "DEFAULT_UI_LOCALE",
    "SUPPORTED_UI_LOCALES",
    "UiPrefsError",
    "load_ui_prefs",
    "patch_ui_prefs",
    "save_ui_prefs",
]
