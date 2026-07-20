"""LLM Token 预估（调用前估算，非事后按响应长度反算）。"""

import json
from dataclasses import dataclass, field
from typing import Any

from core.llm.model.llm_request import LlmRequest


@dataclass(frozen=True)
class TokenEstimate:
    """单次 Chat Completions 调用的 token 预估值。"""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    def to_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class TokenBreakdownItem:
    tokens: int
    pct_of_total: float

    def to_dict(self) -> dict[str, Any]:
        return {"tokens": self.tokens, "pct_of_total": self.pct_of_total}


@dataclass(frozen=True)
class TokenBreakdown:
    system_tokens: int
    tools_tokens: int
    messages_tokens: int
    completion_budget_tokens: int
    prompt_estimated_tokens: int
    total_estimated_tokens: int
    items: dict[str, TokenBreakdownItem] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_tokens": self.system_tokens,
            "tools_tokens": self.tools_tokens,
            "messages_tokens": self.messages_tokens,
            "completion_budget_tokens": self.completion_budget_tokens,
            "prompt_estimated_tokens": self.prompt_estimated_tokens,
            "total_estimated_tokens": self.total_estimated_tokens,
            "breakdown": {k: v.to_dict() for k, v in self.items.items()},
        }


def estimate_text_tokens(text: str) -> int:
    """按中英混排启发式估算文本 token 数。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return max(1, int(cjk / 1.5 + other / 4))


def _message_text(msg: dict[str, Any]) -> str:
    parts: list[str] = []
    content = msg.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                parts.append(json.dumps(block, ensure_ascii=False))
            else:
                parts.append(str(block))
    elif content is not None:
        parts.append(str(content))
    if msg.get("tool_call_id"):
        parts.append(str(msg["tool_call_id"]))
    for tc in msg.get("tool_calls") or []:
        parts.append(json.dumps(tc, ensure_ascii=False))
    return "\n".join(parts)


def _pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(part * 100.0 / total, 1)


def estimate_tools_tokens(tools: list[Any]) -> int:
    if not tools:
        return 0
    payload: list[dict[str, Any]] = []
    for tool in tools:
        if hasattr(tool, "model_dump"):
            payload.append(tool.model_dump())
        elif isinstance(tool, dict):
            payload.append(tool)
        else:
            payload.append({"name": str(tool)})
    return estimate_text_tokens(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def estimate_request_breakdown(
    request: LlmRequest,
    max_completion_tokens: int,
) -> TokenBreakdown:
    system_tokens = estimate_text_tokens(request.system.strip())
    tools_tokens = estimate_tools_tokens(list(request.tools))
    messages_tokens = 0
    for msg in request.messages:
        messages_tokens += estimate_text_tokens(_message_text(msg)) + 4
    completion_budget = max(0, int(max_completion_tokens))
    prompt_total = system_tokens + tools_tokens + messages_tokens
    total = prompt_total + completion_budget
    items = {
        "system": TokenBreakdownItem(system_tokens, _pct(system_tokens, total)),
        "tools": TokenBreakdownItem(tools_tokens, _pct(tools_tokens, total)),
        "messages": TokenBreakdownItem(messages_tokens, _pct(messages_tokens, total)),
        "completion": TokenBreakdownItem(
            completion_budget, _pct(completion_budget, total)
        ),
    }
    return TokenBreakdown(
        system_tokens=system_tokens,
        tools_tokens=tools_tokens,
        messages_tokens=messages_tokens,
        completion_budget_tokens=completion_budget,
        prompt_estimated_tokens=prompt_total,
        total_estimated_tokens=total,
        items=items,
    )


def estimate_chat_tokens(
    messages: list[dict[str, Any]],
    max_completion_tokens: int,
) -> TokenEstimate:
    """
    调用 LLM 前预估 token：
    - prompt：各 message 文本 + tool_calls + 固定开销
    - completion：使用配置的 max_tokens 作为上限预估
    """
    prompt = 0
    for msg in messages:
        prompt += estimate_text_tokens(_message_text(msg)) + 4
    completion = max(0, int(max_completion_tokens))
    return TokenEstimate(prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion)


def normalize_api_usage(usage: dict[str, Any] | None) -> dict[str, Any] | None:
    """Anthropic/OpenAI usage → 统一 prompt/completion/total。"""
    if not usage or not isinstance(usage, dict):
        return None
    prompt = usage.get("prompt_tokens")
    if prompt is None:
        prompt = usage.get("input_tokens")
    completion = usage.get("completion_tokens")
    if completion is None:
        completion = usage.get("output_tokens")
    if prompt is None and completion is None:
        return None
    p = int(prompt or 0)
    c = int(completion or 0)
    return {
        "prompt_tokens": p,
        "completion_tokens": c,
        "total_tokens": p + c,
        "raw": dict(usage),
    }


def build_token_usage_meta(
    breakdown: TokenBreakdown,
    *,
    estimated: bool = True,
    actual_usage: dict[str, Any] | None = None,
    finish_reason: str | None = None,
    finish_reason_normalized: str | None = None,
    truncated: bool | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "estimated": estimated,
        "prompt_tokens": breakdown.system_tokens
        + breakdown.tools_tokens
        + breakdown.messages_tokens,
        "estimated_completion_tokens": breakdown.completion_budget_tokens,
        "total_estimated_tokens": breakdown.total_estimated_tokens,
        **breakdown.to_dict(),
    }
    if estimated:
        meta["completion_tokens"] = None
        meta["total_tokens"] = meta["prompt_tokens"]
    else:
        meta["completion_tokens"] = (
            actual_usage.get("completion_tokens")
            if actual_usage
            else breakdown.completion_budget_tokens
        )
        meta["total_tokens"] = (
            actual_usage.get("total_tokens")
            if actual_usage
            else breakdown.total_estimated_tokens
        )
    if actual_usage:
        meta["actual_usage"] = actual_usage
        meta["actual_prompt_tokens"] = actual_usage.get("prompt_tokens")
        meta["actual_completion_tokens"] = actual_usage.get("completion_tokens")
        meta["actual_total_tokens"] = actual_usage.get("total_tokens")
    if finish_reason:
        meta["finish_reason"] = finish_reason
    if finish_reason_normalized:
        meta["finish_reason_normalized"] = finish_reason_normalized
    if truncated is not None:
        meta["truncated"] = truncated
    return meta
