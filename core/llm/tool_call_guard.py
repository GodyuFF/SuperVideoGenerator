"""tool_calls 占位符检测与纠正提示（LLM 偶发返回 $TOOL_NAME 等文档占位符）。"""

from __future__ import annotations

import re
from typing import Any

from core.llm.client.tool_calls import ToolCallResult

_PLACEHOLDER_NAME_RE = re.compile(r"^\$?TOOL_?NAME$", re.IGNORECASE)
_PLACEHOLDER_ARG_RE = re.compile(
    r"\$PARAMETER|\$TOOL_?NAME|:\s*\$[A-Z_]+",
)


class PlaceholderToolCallError(ValueError):
    """LLM 返回文档占位符式 tool_call，非真实工具调用。"""

    def __init__(self, result: ToolCallResult) -> None:
        self.result = result
        name = result.primary_name()
        raw_args = _raw_arguments(result)
        super().__init__(
            f"占位符 tool_call（name={name!r}, arguments={raw_args[:120]!r}）"
        )


PLACEHOLDER_CORRECTION_USER = (
    "上一轮 tool_calls 无效：不得使用 $TOOL_NAME、$PARAMETER_NAME 等占位符，"
    "arguments 必须是合法 JSON。"
    "请从 available_actions 中选择真实函数名，并按 input_schema 填写参数"
    "（含 plan_status、remaining_plan）。立即重试一次 tool_calls。"
)


def _raw_arguments(result: ToolCallResult) -> str:
    tc = result.primary_tool_call()
    if not tc:
        return ""
    fn = tc.get("function") or {}
    raw = fn.get("arguments", "{}")
    return raw if isinstance(raw, str) else str(raw)


def is_placeholder_tool_call(result: ToolCallResult) -> bool:
    """检测 LLM 是否返回 API 文档式占位符 tool_call。"""
    if not result.tool_calls:
        return False
    name = result.primary_name()
    if not name:
        return False
    if "$" in name or _PLACEHOLDER_NAME_RE.match(name.strip()):
        return True
    raw = _raw_arguments(result)
    if not raw:
        return False
    if _PLACEHOLDER_ARG_RE.search(raw):
        return True
    return False


def assert_not_placeholder_tool_call(result: ToolCallResult) -> None:
    if is_placeholder_tool_call(result):
        raise PlaceholderToolCallError(result)


def format_placeholder_failure(
    result: ToolCallResult,
    *,
    agent_name: str = "",
    allowed_actions: list[str] | None = None,
) -> str:
    """生成最终失败的可读错误信息。"""
    name = result.primary_name()
    raw = _raw_arguments(result)
    parts = [
        f"LLM 返回占位符 tool_call（agent={agent_name or 'unknown'}, name={name!r}）",
        f"arguments 片段: {raw[:200]}",
    ]
    if allowed_actions:
        parts.append(f"允许的行动: {allowed_actions}")
    return "；".join(parts)


def is_placeholder_parse_error(exc: BaseException) -> bool:
    """parse_tool_arguments 失败是否由占位符/非法 JSON 引起（可重试）。"""
    msg = str(exc)
    if "$PARAMETER" in msg or "$TOOL" in msg:
        return True
    if "非合法 JSON" in msg and "$" in msg:
        return True
    return isinstance(exc, PlaceholderToolCallError)
