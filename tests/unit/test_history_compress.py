"""history_compress LLM 摘要压缩测试。"""

import pytest

from core.llm.client.settings import LLMConfigManager
from core.llm.model.chat_message import chat_message
from core.llm.model.llm_request import LlmRequest
from core.llm.prompt.history_compress import (
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
    assert breakdown.total_estimated_tokens == (
        breakdown.system_tokens
        + breakdown.tools_tokens
        + breakdown.messages_tokens
        + breakdown.completion_budget_tokens
    )
    assert "system" in breakdown.items
    assert breakdown.items["completion"].pct_of_total > 0


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
    assert breakdown.total_estimated_tokens > 50
