"""history_compress LLM 摘要压缩测试。"""

import pytest

from core.llm.client.settings import LLMConfigManager
from core.llm.model.chat_message import chat_message
from core.llm.model.llm_request import LlmRequest
from core.llm.prompt.history_compress import (
    _split_for_compression,
    estimate_request_over_window,
    maybe_compress_chat_history,
)
from core.llm.client.tokens import estimate_request_breakdown


class SummaryLLM:
    async def complete(self, request, **kwargs):
        return "用户要做都市情感短片，已确认主角设定。"


@pytest.mark.asyncio
async def test_maybe_compress_skips_when_under_window():
    config = LLMConfigManager()
    config.update(context_window_tokens=1_000_000)
    messages = [chat_message("user", "你好")]
    result = await maybe_compress_chat_history(
        SummaryLLM(),  # type: ignore[arg-type]
        config,
        messages=messages,
        system_prompt="sys",
    )
    assert result == messages


@pytest.mark.asyncio
async def test_prepare_react_chat_history_keeps_full_history_when_under_window():
    """未超窗时 prepare_react_chat_history 应保留完整历史，不做 snippet 滑窗。"""
    from core.llm.prompt.history_compress import prepare_react_chat_history

    config = LLMConfigManager()
    config.update(context_window_tokens=1_000_000)
    messages = [chat_message("user", "你好")]
    result = await prepare_react_chat_history(
        SummaryLLM(),  # type: ignore[arg-type]
        config,
        messages=messages,
        system_prompt="sys",
    )
    assert result == messages


@pytest.mark.asyncio
async def test_prepare_react_chat_history_keeps_long_history_when_under_window():
    """未超输入上限时，长历史也不应被 snippet 截断。"""
    from core.llm.prompt.history_compress import prepare_react_chat_history

    config = LLMConfigManager()
    config.update(context_window_tokens=1_000_000)
    messages = [chat_message("user", f"消息{i}") for i in range(20)]
    result = await prepare_react_chat_history(
        SummaryLLM(),  # type: ignore[arg-type]
        config,
        messages=messages,
        system_prompt="sys",
    )
    assert len(result) == 20


@pytest.mark.asyncio
async def test_maybe_compress_summarizes_older_messages():
    config = LLMConfigManager()
    config.update(context_window_tokens=100, history_keep_messages=2)
    messages = [
        chat_message("user", f"消息{i}" * 50) for i in range(8)
    ]
    system = "x" * 500
    result = await maybe_compress_chat_history(
        SummaryLLM(),  # type: ignore[arg-type]
        config,
        messages=messages,
        system_prompt=system,
    )
    assert len(result) <= 4  # summary assistant + kept
    assert any("较早对话 LLM 摘要" in str(m.get("content", "")) for m in result)


def test_split_for_compression_keeps_tool_turn_atomic():
    from core.llm.model.chat_message import text_block, tool_message, tool_use_block

    messages = [
        chat_message("user", "诉求"),
        chat_message(
            "assistant",
            [tool_use_block(tool_id="call_a", name="finish", input_data={})],
        ),
        tool_message("call_a", "完成"),
    ]
    for i in range(6):
        messages.append(chat_message("assistant", f"填充{i}"))

    kept, older = _split_for_compression(messages, keep=2, pin_first_user=False)
    assert older
    roles = [m.get("role") for m in kept]
    if "tool" in roles:
        tool_index = roles.index("tool")
        assert kept[tool_index - 1]["role"] == "assistant"


def test_estimate_request_breakdown_pct():
    req = LlmRequest(
        system="系统提示",
        tools=[],
        messages=[chat_message("user", "用户输入")],
    )
    breakdown = estimate_request_breakdown(req, max_completion_tokens=8192)
    assert breakdown.system_tokens > 0
    assert breakdown.messages_tokens > 0
    assert breakdown.completion_budget_tokens == 8192
    assert breakdown.prompt_estimated_tokens == (
        breakdown.system_tokens
        + breakdown.tools_tokens
        + breakdown.messages_tokens
    )
    assert breakdown.total_estimated_tokens == (
        breakdown.prompt_estimated_tokens + breakdown.completion_budget_tokens
    )
    assert "system" in breakdown.items
    assert breakdown.items["completion"].pct_of_total > 0


def test_estimate_request_over_window_uses_prompt_only():
    """超窗判定仅比较输入 token，不含输出预算。"""
    config = LLMConfigManager()
    config.update(context_window_tokens=100, max_tokens=8192)
    over, breakdown = estimate_request_over_window(
        system_prompt="短",
        tools=None,
        messages=[chat_message("user", "短")],
        config=config,
    )
    assert over is False
    assert breakdown.prompt_estimated_tokens < 100
    assert breakdown.total_estimated_tokens > breakdown.prompt_estimated_tokens


def test_estimate_request_over_window():
    config = LLMConfigManager()
    config.update(context_window_tokens=50)
    over, breakdown = estimate_request_over_window(
        system_prompt="x" * 200,
        tools=None,
        messages=[chat_message("user", "y" * 200)],
        config=config,
    )
    assert over is True
    assert breakdown.prompt_estimated_tokens > 50
