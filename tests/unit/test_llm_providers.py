"""LLM provider 预设与 OpenAI wire 测试。"""

from core.llm.client.providers import PROVIDER_PRESETS, list_providers, react_tool_choice, resolved_protocol
from core.llm.client.wire_openai import (
    anthropic_tool_choice_to_openai,
    llm_request_to_openai_payload,
    tools_to_openai,
)
from core.llm.model.chat_message import chat_message, tool_use_block
from core.llm.model.llm_request import LlmRequest, ToolDefinition


def test_react_tool_choice_uses_any():
    assert react_tool_choice("deepseek") == {"type": "any"}
    assert react_tool_choice("openai") == {"type": "any"}


def test_all_planned_providers_registered():
    expected = {
        "deepseek",
        "anthropic",
        "openai",
        "openrouter",
        "moonshot",
        "zhipu",
        "dashscope",
    }
    assert set(PROVIDER_PRESETS) == expected


def test_provider_protocols():
    assert resolved_protocol("deepseek") == "anthropic"
    assert resolved_protocol("anthropic") == "anthropic"
    assert resolved_protocol("openai") == "openai"
    assert resolved_protocol("openrouter") == "openai"
    assert resolved_protocol("moonshot") == "openai"
    assert resolved_protocol("zhipu") == "openai"
    assert resolved_protocol("dashscope") == "openai"


def test_deepseek_uses_anthropic_endpoint():
    assert PROVIDER_PRESETS["deepseek"].base_url.endswith("/anthropic")


def test_list_providers_includes_protocol():
    providers = list_providers()
    assert len(providers) == 7
    openai_row = next(p for p in providers if p["id"] == "openai")
    assert openai_row["protocol"] == "openai"


def test_anthropic_tool_choice_to_openai():
    assert anthropic_tool_choice_to_openai({"type": "any"}) == "required"
    assert anthropic_tool_choice_to_openai({"type": "auto"}) == "auto"
    assert anthropic_tool_choice_to_openai({"type": "tool", "name": "scan_text_assets"}) == {
        "type": "function",
        "function": {"name": "scan_text_assets"},
    }


def test_tools_to_openai_shape():
    tools = [
        ToolDefinition(
            name="scan_text_assets",
            description="扫描待生图资产",
            input_schema={"type": "object", "properties": {}},
        )
    ]
    wire = tools_to_openai(tools)
    assert wire[0]["type"] == "function"
    assert wire[0]["function"]["name"] == "scan_text_assets"
    assert wire[0]["function"]["parameters"]["type"] == "object"


def test_openai_payload_includes_system_and_tool_choice():
    request = LlmRequest(
        system="你是助手",
        tools=[
            ToolDefinition(
                name="ask_user_question",
                description="提问",
                input_schema={"type": "object", "properties": {}},
            )
        ],
        messages=[chat_message("user", "你好")],
        tool_choice={"type": "any"},
    )
    payload = llm_request_to_openai_payload(
        request,
        model="gpt-4.1",
        temperature=0.2,
        max_tokens=1024,
        stream=True,
    )
    assert payload["model"] == "gpt-4.1"
    assert payload["tool_choice"] == "required"
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][0]["content"] == "你是助手"


def test_openai_payload_serializes_assistant_tool_calls():
    request = LlmRequest(
        system="",
        tools=[],
        messages=[
            chat_message(
                "assistant",
                [
                    tool_use_block(
                        tool_id="call_1",
                        name="generate_images",
                        input_data={"asset_ids": ["a1"]},
                    )
                ],
            ),
            chat_message("tool", "完成", tool_call_id="call_1"),
        ],
        tool_choice=None,
    )
    payload = llm_request_to_openai_payload(
        request,
        model="gpt-4.1",
        temperature=0.2,
        max_tokens=1024,
    )
    assistant = payload["messages"][0]
    assert assistant["role"] == "assistant"
    assert assistant["tool_calls"][0]["function"]["name"] == "generate_images"
    assert payload["messages"][1]["role"] == "tool"
