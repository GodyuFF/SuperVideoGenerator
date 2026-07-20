"""MCP guard 与 adapter 单元测试（无真实 MCP Server）。"""

from core.extensions.mcp.guard import (
    mcp_result_to_observation,
    mcp_tool_registry_name,
    parse_mcp_tool_name,
    truncate_mcp_text,
    validate_server_config,
)


def test_mcp_tool_registry_name():
    assert mcp_tool_registry_name("github", "search_code") == "mcp.github.search_code"


def test_parse_mcp_tool_name_roundtrip():
    name = mcp_tool_registry_name("github", "search_code")
    parsed = parse_mcp_tool_name(name)
    assert parsed == ("github", "search_code")


def test_validate_stdio_requires_command():
    try:
        validate_server_config("", "stdio", "")
        assert False, "应抛出 ValueError"
    except ValueError as e:
        assert "command" in str(e)


def test_validate_sse_rejects_localhost():
    try:
        validate_server_config("", "sse", "http://localhost:8080/sse")
        assert False, "应拒绝 localhost"
    except ValueError as e:
        assert "内网" in str(e) or "localhost" in str(e).lower()


def test_truncate_mcp_text():
    assert truncate_mcp_text("abc", limit=10) == "abc"
    long_text = "x" * 100
    assert truncate_mcp_text(long_text, limit=20).endswith("…")


class _FakeTextBlock:
    type = "text"
    text = "hello mcp"


class _FakeResult:
    content = [_FakeTextBlock()]
    isError = False
    structuredContent = {"ok": True}


def test_mcp_result_to_observation():
    obs, structured = mcp_result_to_observation(_FakeResult())
    assert "hello mcp" in obs
    assert structured["valid"] is True
    assert structured["source"] == "mcp"
