"""扩展发现与 Tool 注册单元测试。"""

from __future__ import annotations

import pytest

from core.extensions.protocol import SkillToolManifest
from core.extensions.tool_filter import apply_skill_tool_filter
from core.llm.tools import get_tool_registry, reset_tool_registry


@pytest.fixture(autouse=True)
def _fresh_registry():
    reset_tool_registry()
    yield
    reset_tool_registry()


def test_web_search_extension_registered():
    registry = get_tool_registry()
    spec = registry.get("web_search")
    assert spec is not None
    assert spec.source == "extension"
    assert spec.agent == "common"
    assert spec.read_only


def test_skill_tool_manifest_from_dict():
    manifest = SkillToolManifest.from_dict(
        {
            "enable": ["web_search"],
            "agents": {"script_agent": ["read_webpage", "web_search"]},
            "exclude": ["delete_plot"],
        }
    )
    assert manifest is not None
    assert manifest.enable == ["web_search"]
    assert manifest.enabled_tools_for_agent("script_agent") == [
        "read_webpage",
        "web_search",
    ]
    assert manifest.enabled_tools_for_agent("image_agent") is None


def test_apply_skill_tool_filter_whitelist():
    overlay = {
        "tool_manifest": {
            "agents": {"script_agent": ["list_text_assets", "web_search"]},
        }
    }
    actions = ["parse_brief", "list_text_assets", "create_plot", "web_search"]
    filtered = apply_skill_tool_filter("script_agent", actions, overlay)
    assert filtered == ["list_text_assets", "web_search"]


def test_apply_skill_tool_filter_enable_append():
    overlay = {"tool_manifest": {"enable": ["web_search"]}}
    actions = ["parse_brief", "list_text_assets"]
    filtered = apply_skill_tool_filter("script_agent", actions, overlay)
    assert "web_search" in filtered
    assert "parse_brief" in filtered


def test_list_tools_filter_by_source():
    registry = get_tool_registry()
    ext_tools = registry.list_tools(sources={"extension"})
    assert any(s.name == "web_search" for s in ext_tools)
    builtin_tools = registry.list_tools(sources={"builtin"})
    assert all(s.source == "builtin" for s in builtin_tools)
