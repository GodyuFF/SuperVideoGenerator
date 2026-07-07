"""LLM provider 预设与 tool_choice 适配测试。"""

from core.llm.client.providers import PROVIDER_PRESETS, react_tool_choice


def test_react_tool_choice_uses_any():
    assert react_tool_choice("deepseek") == {"type": "any"}
    assert react_tool_choice("anthropic") == {"type": "any"}


def test_only_deepseek_and_anthropic_providers():
    assert set(PROVIDER_PRESETS) == {"deepseek", "anthropic"}
    assert PROVIDER_PRESETS["deepseek"].base_url.endswith("/anthropic")
