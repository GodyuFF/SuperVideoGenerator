"""性能观测日志单元测试。"""

import logging

import pytest

from core.logging import perf as perf_mod


@pytest.fixture(autouse=True)
def _reset_perf_env(monkeypatch):
    """每个用例恢复默认 perf 开关。"""
    monkeypatch.delenv("SVG_PERF_LOG", raising=False)


def test_perf_enabled_default():
    """默认开启性能日志。"""
    assert perf_mod.perf_enabled() is True


def test_perf_disabled_by_env(monkeypatch):
    """SVG_PERF_LOG=0 时关闭性能日志。"""
    monkeypatch.setenv("SVG_PERF_LOG", "0")
    assert perf_mod.perf_enabled() is False


def test_log_perf_writes_message(caplog):
    """log_perf 输出 [PERF:类别] 结构化行。"""
    caplog.set_level(logging.INFO)
    perf_mod.log_perf("test", "hello", duration_ms=12.34, foo="bar")
    assert "[PERF:test] hello" in caplog.text
    assert "duration_ms=12.3" in caplog.text
    assert "foo=bar" in caplog.text


def test_log_perf_skipped_when_disabled(monkeypatch, caplog):
    """关闭 perf 时不写日志。"""
    monkeypatch.setenv("SVG_PERF_LOG", "0")
    caplog.set_level(logging.INFO)
    perf_mod.log_perf("test", "hidden")
    assert caplog.text == ""


def test_perf_span_logs_duration(caplog):
    """PerfSpan 退出时自动记录耗时。"""
    caplog.set_level(logging.INFO)
    with perf_mod.PerfSpan("startup", "phase", step="a"):
        pass
    assert "[PERF:startup] phase" in caplog.text
    assert "duration_ms=" in caplog.text
    assert "step=a" in caplog.text


@pytest.mark.asyncio
async def test_async_perf_span_logs_duration(caplog):
    """AsyncPerfSpan 退出时自动记录耗时。"""
    caplog.set_level(logging.INFO)
    async with perf_mod.AsyncPerfSpan("chat", "task", script_id="s1"):
        pass
    assert "[PERF:chat] task" in caplog.text
    assert "script_id=s1" in caplog.text
