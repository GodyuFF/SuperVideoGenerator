"""LLM tool_calls 流式解析与重试请求测试。"""

import json

from core.llm.client.client import _tool_calls_response_log_body, _tool_calls_retry_request
from core.llm.streaming import ToolCallAccumulator, parse_sse_line
from core.llm.client.tool_calls import ToolCallResult
from core.llm.prompt.chat_messages import build_llm_request
from core.llm.protocol import parse_react_tool_calls


def test_parse_sse_line_collects_anthropic_usage_and_text():
    line = (
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},'
        '"usage":{"input_tokens":1,"output_tokens":2}}'
    )
    delta, meta = parse_sse_line(line)
    assert delta is None
    assert meta["finish_reason"] == "end_turn"
    assert meta["usage"]["output_tokens"] == 2


def test_parse_sse_line_anthropic_thinking_delta():
    line = (
        'data: {"type":"content_block_delta","index":0,'
        '"delta":{"type":"thinking_delta","thinking":"想"}}'
    )
    delta, meta = parse_sse_line(line)
    assert delta == {"anthropic_thinking_delta": {"index": 0, "thinking": "想"}}
    assert meta == {}


def test_parse_sse_line_anthropic_text_delta():
    line = (
        'data: {"type":"content_block_delta","index":0,'
        '"delta":{"type":"text_delta","text":"hi"}}'
    )
    delta, meta = parse_sse_line(line)
    assert delta == {"content": "hi"}
    assert meta == {}


def test_tool_call_accumulator_anthropic_thinking():
    acc = ToolCallAccumulator()
    acc.feed(
        {
            "anthropic_thinking_start": {
                "index": 0,
                "thinking": "先",
                "signature": "sig",
            }
        }
    )
    acc.feed({"anthropic_thinking_delta": {"index": 0, "thinking": "分析"}})
    acc.feed({"content": "对外说明"})
    acc.feed(
        {
            "anthropic_tool_use_start": {
                "index": 1,
                "id": "toolu_1",
                "name": "finish",
                "input": {},
            }
        }
    )
    result = acc.build()
    assert result.thinking == "先分析"
    assert result.content == "对外说明"
    assert result.raw_message["content"][0]["type"] == "thinking"
    assert result.raw_message["content"][0]["thinking"] == "先分析"
    assert result.raw_message["content"][0]["signature"] == "sig"
    decision = parse_react_tool_calls(result)
    assert decision.thought == "先分析"


def test_tool_call_accumulator_anthropic_tool_use():
    acc = ToolCallAccumulator()
    acc.absorb_meta({"finish_reason": "tool_use", "usage": {"total_tokens": 10}})
    acc.feed({"content": "先委派"})
    acc.feed(
        {
            "anthropic_tool_use_start": {
                "index": 0,
                "id": "toolu_1",
                "name": "delegate_script_design",
                "input": {},
            }
        }
    )
    acc.feed(
        {
            "anthropic_input_json_delta": {
                "index": 0,
                "partial_json": '{"observation":"ok"}',
            }
        }
    )
    result = acc.build()
    assert result.tool_calls
    assert result.tool_calls[0]["function"]["name"] == "delegate_script_design"
    args = result.tool_calls[0]["function"]["arguments"]
    assert json.loads(args) == {"observation": "ok"}
    assert parse_react_tool_calls(result).action_input == {"observation": "ok"}
    assert result.raw_message["stream_meta"]["finish_reason"] == "tool_use"


def test_tool_call_accumulator_skips_delta_when_start_has_full_input():
    """DeepSeek Anthropic 兼容层可能在 content_block_start 带完整 input 后再发尾部 delta。"""
    payload = {
        "observation": "创建道具",
        "asset_name": "野鹿",
        "content": {"summary": "被捕食对象"},
        "plan_status": "进行中",
        "remaining_plan": ["写剧本"],
    }
    acc = ToolCallAccumulator()
    acc.feed(
        {
            "anthropic_tool_use_start": {
                "index": 0,
                "id": "toolu_1",
                "name": "create_prop",
                "input": payload,
            }
        }
    )
    acc.feed(
        {
            "anthropic_input_json_delta": {
                "index": 0,
                "partial_json": "}",
            }
        }
    )
    result = acc.build()
    args = result.tool_calls[0]["function"]["arguments"]
    assert json.loads(args) == payload
    decision = parse_react_tool_calls(result)
    assert decision.action == "create_prop"
    assert decision.action_input["asset_name"] == "野鹿"


def test_tool_calls_response_log_body_includes_all_fields():
    result = ToolCallResult(
        content="推理",
        tool_calls=[{"id": "c1", "function": {"name": "finish", "arguments": "{}"}}],
        raw_message={"role": "assistant", "content": "推理"},
    )
    body = _tool_calls_response_log_body(
        result, {"finish_reason": "tool_use", "usage": {"total_tokens": 5}}
    )
    assert body["content"] == "推理"
    assert body["tool_calls"]
    assert body["finish_reason"] == "tool_use"
    assert body["usage"]["total_tokens"] == 5


def test_tool_calls_response_log_body_marks_truncation():
    result = ToolCallResult(
        content="",
        tool_calls=[],
        raw_message={"role": "assistant", "content": ""},
    )
    body = _tool_calls_response_log_body(
        result,
        {"finish_reason": "max_tokens", "usage": {"output_tokens": 1024}},
        max_tokens=1024,
    )
    assert body["truncated"] is True
    assert body["finish_reason_normalized"] == "length"
    assert "abort_reason" in body


def test_tool_calls_retry_request_appends_nudge_user_message():
    req = build_llm_request(
        system_prompt="sys",
        history=[{"role": "user", "content": [{"type": "text", "text": "你好"}]}],
    )
    retry = _tool_calls_retry_request(req, "我是助手，请问需要什么？")
    assert retry.messages[-2]["role"] == "assistant"
    assert retry.messages[-1]["role"] == "user"
    assert "tool_use" in retry.messages[-1]["content"][0]["text"]
