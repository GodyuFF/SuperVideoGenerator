"""Thinking 模式下 tool_choice 适配（any/tool → auto）。"""

from __future__ import annotations

from typing import Any

# 模型名包含以下片段时视为 thinking / 推理模型（不区分大小写）
_THINKING_MODEL_HINTS: tuple[str, ...] = (
    "deepseek-reasoner",
    "deepseek-r1",
    "deepseek-v4",
    "deepseek-reason",
    "o1-preview",
    "o1-mini",
    "o3-mini",
    "o3-",
    "qwq",
    "-thinking",
    "thinking-",
)

_FORCED_TOOL_CHOICE_TYPES = frozenset({"any", "tool", "required"})


def is_thinking_model(model: str) -> bool:
    """根据模型名推断是否为 thinking / 推理模型。"""
    name = (model or "").strip().lower()
    if not name:
        return False
    return any(hint in name for hint in _THINKING_MODEL_HINTS)


def is_forced_tool_choice(tool_choice: dict[str, Any] | None) -> bool:
    if not tool_choice:
        return False
    choice_type = str(tool_choice.get("type", "")).strip().lower()
    return choice_type in _FORCED_TOOL_CHOICE_TYPES


def adapt_tool_choice_for_thinking(
    tool_choice: dict[str, Any] | None,
    *,
    thinking_mode: bool,
) -> dict[str, Any] | None:
    """
    Thinking 模式不支持强制 tool_choice（any / tool / required）。
    降级为 auto，由 prompt 约束模型调用 tool。
    """
    if not thinking_mode or tool_choice is None:
        return tool_choice
    if not is_forced_tool_choice(tool_choice):
        return tool_choice
    return {"type": "auto"}


def resolve_thinking_mode(
    model: str,
    *,
    override: bool | None = None,
) -> bool:
    """
    是否启用 thinking 模式 tool_choice 适配。
    override: True/False 强制；None 则按模型名推断。
    """
    if override is not None:
        return override
    return is_thinking_model(model)


def react_tool_choice_intent(provider_id: str) -> dict[str, str]:
    """ReAct 决策期望的 tool_choice（非 thinking 时发送）。"""
    _ = provider_id
    return {"type": "any"}


def action_tool_choice_intent(action: str) -> dict[str, str]:
    """单 action 执行期望的 tool_choice（非 thinking 时发送）。"""
    return {"type": "tool", "name": action}


def resolve_react_tool_choice(
    provider_id: str,
    model: str,
    *,
    thinking_override: bool | None = None,
) -> dict[str, str]:
    intent = react_tool_choice_intent(provider_id)
    adapted = adapt_tool_choice_for_thinking(
        intent,
        thinking_mode=resolve_thinking_mode(model, override=thinking_override),
    )
    assert adapted is not None
    return adapted  # type: ignore[return-value]


def resolve_action_tool_choice(
    action: str,
    model: str,
    *,
    thinking_override: bool | None = None,
) -> dict[str, str]:
    intent = action_tool_choice_intent(action)
    adapted = adapt_tool_choice_for_thinking(
        intent,
        thinking_mode=resolve_thinking_mode(model, override=thinking_override),
    )
    assert adapted is not None
    return adapted  # type: ignore[return-value]
