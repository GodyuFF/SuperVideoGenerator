"""core.logging.setup 单元测试。"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from core.logging.setup import (
    SafeRotatingFileHandler,
    _should_attach_file_handler,
    setup_logging,
)


def test_safe_rotating_file_handler_skips_locked_rollover(tmp_path: Path, monkeypatch) -> None:
    log_path = tmp_path / "app.log"
    log_path.write_text("x" * 64, encoding="utf-8")
    handler = SafeRotatingFileHandler(
        log_path,
        maxBytes=32,
        backupCount=1,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))

    def locked_rename(source: str, dest: str) -> None:
        raise PermissionError(32, "locked")

    monkeypatch.setattr(os, "rename", locked_rename)
    handler.doRollover()


def test_should_attach_file_handler_respects_log_file_off(monkeypatch) -> None:
    monkeypatch.delenv("LOG_FILE", raising=False)
    monkeypatch.setenv("LOG_FILE", "off")
    assert _should_attach_file_handler() is False


def test_should_attach_file_handler_skips_reload_parent(monkeypatch) -> None:
    monkeypatch.delenv("LOG_FILE", raising=False)
    monkeypatch.setenv("LOG_FILE", "data/logs/app.log")
    monkeypatch.setattr("core.logging.setup._reload_enabled", lambda: True)
    monkeypatch.setattr(
        "multiprocessing.current_process",
        lambda: type("P", (), {"name": "MainProcess"})(),
    )
    assert _should_attach_file_handler() is False


def test_setup_logging_uses_safe_handler(tmp_path: Path, monkeypatch) -> None:
    log_file = tmp_path / "app.log"
    monkeypatch.setenv("LOG_FILE", str(log_file))
    monkeypatch.setattr("core.logging.setup._reload_enabled", lambda: False)
    setup_logging("INFO")
    root = logging.getLogger()
    file_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
    assert len(file_handlers) == 1
    assert isinstance(file_handlers[0], SafeRotatingFileHandler)
