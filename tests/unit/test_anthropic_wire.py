"""Anthropic canonical ↔ wire 转换测试。"""

from core.llm.model.chat_message import (
    anthropic_to_canonical_messages,
    canonical_to_anthropic_messages,
    chat_message,
    text_block,
    tool_message,
    tool_result_block,
    tool_use_block,
    wire_message_chars_anthropic,
)


def test_canonical_to_anthropic_assistant_tool_use_and_result():
    canonical = [
        {
            "role": "assistant",
            "content": [
                text_block("思考"),
                tool_use_block(tool_id="call_1", name="finish", input_data={}),
            ],
        },
        tool_message("call_1", "完成"),
    ]
    wire = canonical_to_anthropic_messages(canonical)
    assert len(wire) == 2
    assert wire[0]["role"] == "assistant"
    assert wire[0]["content"][0]["type"] == "thinking"
    assert wire[0]["content"][0]["thinking"] == "思考"
    assert wire[0]["content"][1]["type"] == "tool_use"
    assert wire[1]["role"] == "user"
    assert wire[1]["content"][0]["type"] == "tool_result"
    assert wire[1]["content"][0]["tool_use_id"] == "call_1"


def test_orphan_tool_result_merges_into_user_message():
    canonical = [
        {"role": "assistant", "content": [text_block("先写剧本")]},
        {
            "role": "assistant",
            "content": [
                tool_result_block(tool_use_id="call_unknown", content="失败"),
            ],
        },
    ]
    wire = canonical_to_anthropic_messages(canonical)
    assert wire[0]["role"] == "assistant"
    assert wire[1]["role"] == "user"
    assert wire[1]["content"][0]["type"] == "tool_result"


def test_anthropic_to_canonical_roundtrip():
    wire = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "想"},
                {
                    "type": "tool_use",
                    "id": "c1",
                    "name": "finish",
                    "input": {},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "c1", "content": "ok"},
            ],
        },
    ]
    canonical = anthropic_to_canonical_messages(wire)
    assert len(canonical) == 2
    assert canonical[0]["role"] == "assistant"
    assert canonical[1]["role"] == "tool"
    assert canonical[1]["tool_call_id"] == "c1"


def test_wire_message_chars_anthropic_counts_json():
    msg = {"role": "user", "content": [{"type": "text", "text": "hi"}]}
    assert wire_message_chars_anthropic(msg) > 0


def test_adjacent_user_messages_merge():
    canonical = [
        chat_message("user", "a"),
        tool_message("t1", "obs"),
    ]
    wire = canonical_to_anthropic_messages(canonical)
    assert len(wire) == 1
    assert wire[0]["role"] == "user"
    assert len(wire[0]["content"]) == 2
