"""LlmRequest 与 Anthropic wire 转换测试。"""

from core.llm.client.wire import (
    llm_request_to_log_body,
    llm_request_to_wire_messages,
    llm_request_to_wire_payload,
    tools_to_anthropic,
)
from core.llm.model.llm_request import LlmRequest, ToolDefinition
from core.llm.model.chat_message import chat_message
from core.llm.prompt.chat_messages import build_llm_request


def test_build_llm_request_excludes_system_from_messages():
    req = build_llm_request(
        system_prompt="你是助手",
        history=[chat_message("user", "你好")],
    )
    assert req.system == "你是助手"
    assert len(req.messages) == 1
    assert req.messages[0]["role"] == "user"
    assert all(m.get("role") != "system" for m in req.messages)


def test_log_body_separates_system_tools_messages():
    tool = ToolDefinition(
        name="parse_brief",
        description="解析简报",
        input_schema={"type": "object", "properties": {}},
    )
    req = LlmRequest(
        system="system text",
        tools=[tool],
        messages=[chat_message("user", "hi")],
        tool_choice={"type": "tool", "name": "parse_brief"},
    )
    body = llm_request_to_log_body(req, model="claude-sonnet", stream=True)
    assert body["system"] == "system text"
    assert body["messages"][0]["role"] == "user"
    assert body["tools"][0]["name"] == "parse_brief"
    assert "system" not in str(body["messages"][0].get("role"))
    assert body["tool_choice"]["name"] == "parse_brief"


def test_wire_payload_system_at_top_level():
    req = build_llm_request(
        system_prompt="sys",
        tools=[
            ToolDefinition(
                name="finish",
                description="结束",
                input_schema={"type": "object", "properties": {}},
            )
        ],
        history=[chat_message("user", "u1")],
    )
    payload = llm_request_to_wire_payload(
        req, model="m", temperature=0.1, max_tokens=100
    )
    assert payload["system"] == "sys"
    assert payload["messages"][0]["role"] == "user"
    assert payload["tools"][0]["name"] == "finish"
    assert payload["tools"][0]["input_schema"]["type"] == "object"


def test_tools_to_anthropic_maps_input_schema():
    tool = ToolDefinition(
        name="create_plot",
        description="创建剧情",
        input_schema={
            "type": "object",
            "properties": {"observation": {"type": "string"}},
            "required": ["observation"],
        },
    )
    wire = tools_to_anthropic([tool])[0]
    assert wire["name"] == "create_plot"
    assert wire["input_schema"]["required"] == ["observation"]


def test_wire_messages_exclude_system():
    req = build_llm_request(system_prompt="S", history=[chat_message("user", "U")])
    wire = llm_request_to_wire_messages(req)
    assert wire[0]["role"] == "user"
    assert all(m.get("role") != "system" for m in wire)
