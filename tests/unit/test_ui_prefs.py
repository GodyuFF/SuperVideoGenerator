"""UI 偏好单源：data/ui_prefs.json 读写与校验。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.prefs.ui_prefs import (
    DEFAULT_UI_LOCALE,
    UiPrefsError,
    load_ui_prefs,
    normalize_ui_locale,
    patch_ui_prefs,
    save_ui_prefs,
    ui_prefs_path,
)


def test_normalize_ui_locale_accepts_supported() -> None:
    """支持的语言应原样返回。"""
    assert normalize_ui_locale("zh-CN") == "zh-CN"
    assert normalize_ui_locale("en") == "en"


def test_normalize_ui_locale_rejects_unknown() -> None:
    """非法语言应抛错。"""
    with pytest.raises(UiPrefsError):
        normalize_ui_locale("fr")


def test_load_ui_prefs_defaults_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """无文件时返回默认 zh-CN。"""
    import core.prefs.ui_prefs as mod

    monkeypatch.setattr(mod, "DATA_ROOT", tmp_path)
    assert load_ui_prefs() == {"ui_locale": DEFAULT_UI_LOCALE}
    assert not ui_prefs_path().exists()


def test_save_and_load_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """写入后读取应一致。"""
    import core.prefs.ui_prefs as mod

    monkeypatch.setattr(mod, "DATA_ROOT", tmp_path)
    saved = save_ui_prefs({"ui_locale": "en"})
    assert saved == {"ui_locale": "en"}
    assert load_ui_prefs()["ui_locale"] == "en"
    raw = json.loads(ui_prefs_path().read_text(encoding="utf-8"))
    assert raw["ui_locale"] == "en"


def test_patch_ui_prefs_updates_locale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """PATCH 仅更新传入字段。"""
    import core.prefs.ui_prefs as mod

    monkeypatch.setattr(mod, "DATA_ROOT", tmp_path)
    save_ui_prefs({"ui_locale": "zh-CN"})
    out = patch_ui_prefs({"ui_locale": "en"})
    assert out["ui_locale"] == "en"


def test_load_ui_prefs_recovers_corrupt_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """损坏 JSON 回退默认。"""
    import core.prefs.ui_prefs as mod

    monkeypatch.setattr(mod, "DATA_ROOT", tmp_path)
    path = tmp_path / "ui_prefs.json"
    path.write_text("{not-json", encoding="utf-8")
    assert load_ui_prefs()["ui_locale"] == DEFAULT_UI_LOCALE
