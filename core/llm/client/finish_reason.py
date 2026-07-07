"""LLM finish_reason / stop_reason 归一化与截断判定。"""

from __future__ import annotations

# Anthropic stop_reason → 统一语义
_NORMALIZE_MAP: dict[str, str] = {
    "end_turn": "stop",
    "tool_use": "tool_calls",
    "max_tokens": "length",
    "stop_sequence": "stop",
    # OpenAI / 通用
    "stop": "stop",
    "length": "length",
    "tool_calls": "tool_calls",
    "function_call": "tool_calls",
    "content_filter": "content_filter",
}

_TRUNCATED_REASONS = frozenset({"max_tokens", "length"})


def normalize_finish_reason(finish_reason: str | None) -> str:
    if not finish_reason:
        return ""
    key = str(finish_reason).strip().lower()
    return _NORMALIZE_MAP.get(key, key)


def is_output_truncated(finish_reason: str | None) -> bool:
    if not finish_reason:
        return False
    raw = str(finish_reason).strip().lower()
    return raw in _TRUNCATED_REASONS or normalize_finish_reason(raw) == "length"


def describe_finish_reason(
    finish_reason: str | None,
    *,
    output_tokens: int | None = None,
    max_tokens: int | None = None,
) -> str:
    raw = str(finish_reason or "").strip() or "unknown"
    normalized = normalize_finish_reason(raw) or raw
    if is_output_truncated(raw):
        out = output_tokens if output_tokens is not None else "?"
        cap = max_tokens if max_tokens is not None else "?"
        return (
            f"输出在 max_tokens 处被截断（finish_reason={raw}，"
            f"已输出约 {out} tokens，上限 {cap}）。"
            "请提高 max_tokens、缩短 thinking/输入，或启用对话压缩。"
        )
    if normalized == "tool_calls":
        return f"模型以 tool 调用结束（{raw}）。"
    if normalized == "stop":
        return f"模型正常结束（{raw}）。"
    if normalized == "content_filter":
        return f"内容被安全策略拦截（{raw}）。"
    return f"模型结束原因：{raw}（归一化：{normalized}）。"


class LlmOutputTruncatedError(RuntimeError):
    """completion 因 max_tokens/length 截断，无法完成 tool_calls 或完整输出。"""

    def __init__(
        self,
        finish_reason: str | None,
        *,
        output_tokens: int | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self.finish_reason = finish_reason
        self.output_tokens = output_tokens
        self.max_tokens = max_tokens
        super().__init__(
            describe_finish_reason(
                finish_reason,
                output_tokens=output_tokens,
                max_tokens=max_tokens,
            )
        )
