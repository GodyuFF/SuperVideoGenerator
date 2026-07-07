"""finish_reason 归一化与截断判定测试。"""

import pytest

from core.llm.client.finish_reason import (
    LlmOutputTruncatedError,
    describe_finish_reason,
    is_output_truncated,
    normalize_finish_reason,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("end_turn", "stop"),
        ("tool_use", "tool_calls"),
        ("max_tokens", "length"),
        ("length", "length"),
        ("stop", "stop"),
    ],
)
def test_normalize_finish_reason(raw, expected):
    assert normalize_finish_reason(raw) == expected


@pytest.mark.parametrize(
    "raw,truncated",
    [
        ("max_tokens", True),
        ("length", True),
        ("end_turn", False),
        ("tool_use", False),
        (None, False),
    ],
)
def test_is_output_truncated(raw, truncated):
    assert is_output_truncated(raw) is truncated


def test_describe_finish_reason_truncated():
    msg = describe_finish_reason("max_tokens", output_tokens=1024, max_tokens=8192)
    assert "截断" in msg
    assert "1024" in msg


def test_llm_output_truncated_error_message():
    err = LlmOutputTruncatedError("max_tokens", output_tokens=512, max_tokens=1024)
    assert "512" in str(err)
    assert err.finish_reason == "max_tokens"
