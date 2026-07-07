"""complete_tool_calls max_tokens 截断 abort 测试。"""

from contextlib import asynccontextmanager
from typing import Any

import pytest

from core.llm.client.client import LLMClient
from core.llm.client.finish_reason import LlmOutputTruncatedError
from core.llm.client.settings import LLMConfigManager
from core.llm.model.llm_request import LlmRequest, ToolDefinition
from core.llm.prompt.chat_messages import build_llm_request


class _FakeStreamResponse:
    status_code = 200

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self.headers: dict[str, str] = {}

    async def aread(self) -> bytes:
        return b""

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeAsyncClient:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    @asynccontextmanager
    async def stream(self, method: str, url: str, **kwargs):
        yield _FakeStreamResponse(self._lines)


@pytest.mark.asyncio
async def test_complete_tool_calls_aborts_on_max_tokens(monkeypatch):
    sse_lines = [
        'data: {"type":"message_start","message":{"id":"msg_1","usage":{"input_tokens":1,"output_tokens":0}}}',
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"思考中"}}',
        'data: {"type":"message_delta","delta":{"stop_reason":"max_tokens"},"usage":{"output_tokens":1024}}',
    ]

    def fake_client(**kwargs):
        return _FakeAsyncClient(sse_lines)

    monkeypatch.setattr("core.llm.client.client.httpx.AsyncClient", fake_client)

    config = LLMConfigManager()
    config.update(api_key="test-key", max_tokens=1024)
    client = LLMClient(config)
    req = build_llm_request(
        system_prompt="sys",
        tools=[
            ToolDefinition(
                name="finish",
                description="结束",
                input_schema={"type": "object", "properties": {}},
            )
        ],
        history=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
    )

    with pytest.raises(LlmOutputTruncatedError) as exc:
        await client.complete_tool_calls(req, log_context={"project_id": "p1"})

    assert exc.value.finish_reason == "max_tokens"
    assert "截断" in str(exc.value)
