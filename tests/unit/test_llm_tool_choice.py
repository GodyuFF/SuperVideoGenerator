"""Thinking 模式 tool_choice 适配测试。"""

from core.llm.client.settings import LLMConfigManager, LLMSettings
from core.llm.client.tool_choice import (
    adapt_tool_choice_for_thinking,
    is_thinking_model,
    resolve_action_tool_choice,
    resolve_react_tool_choice,
)
from core.llm.client.providers import react_tool_choice


def test_is_thinking_model_detects_reasoner():
    assert is_thinking_model("deepseek-reasoner")
    assert is_thinking_model("DeepSeek-V4-Pro")
    assert not is_thinking_model("deepseek-chat")
    assert not is_thinking_model("claude-sonnet-4-20250514")


def test_adapt_downgrades_any_and_tool():
    assert adapt_tool_choice_for_thinking(
        {"type": "any"}, thinking_mode=True
    ) == {"type": "auto"}
    assert adapt_tool_choice_for_thinking(
        {"type": "tool", "name": "parse_brief"}, thinking_mode=True
    ) == {"type": "auto"}
    assert adapt_tool_choice_for_thinking(
        {"type": "any"}, thinking_mode=False
    ) == {"type": "any"}


def test_resolve_react_tool_choice_thinking_vs_chat():
    assert resolve_react_tool_choice("deepseek", "deepseek-chat") == {"type": "any"}
    assert resolve_react_tool_choice("deepseek", "deepseek-reasoner") == {
        "type": "auto"
    }


def test_resolve_action_tool_choice_thinking():
    assert resolve_action_tool_choice("create_plot", "deepseek-chat") == {
        "type": "tool",
        "name": "create_plot",
    }
    assert resolve_action_tool_choice("create_plot", "deepseek-v4-flash") == {
        "type": "auto"
    }


def test_llm_config_manager_adapts_on_thinking_model():
    mgr = LLMConfigManager()
    mgr._settings = LLMSettings(model="deepseek-reasoner")
    assert mgr.is_thinking_mode() is True
    assert mgr.adapt_tool_choice({"type": "any"}) == {"type": "auto"}


def test_llm_config_thinking_mode_override():
    mgr = LLMConfigManager()
    mgr._settings = LLMSettings(model="deepseek-chat", thinking_mode=True)
    assert mgr.is_thinking_mode() is True
    assert mgr.adapt_tool_choice({"type": "tool", "name": "finish"}) == {
        "type": "auto"
    }


def test_react_tool_choice_intent_unchanged_for_non_thinking():
    assert react_tool_choice("deepseek") == {"type": "any"}
