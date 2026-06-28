"""LLM Token 预估（调用前估算，非事后按响应长度反算）。"""

from dataclasses import dataclass


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


def estimate_text_tokens(text: str) -> int:
    """按中英混排启发式估算文本 token 数。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return max(1, int(cjk / 1.5 + other / 4))


def estimate_chat_tokens(
    messages: list[dict[str, str]],
    max_completion_tokens: int,
) -> TokenEstimate:
    """
    调用 LLM 前预估 token：
    - prompt：各 message content + 固定开销
    - completion：使用配置的 max_tokens 作为上限预估
    """
    prompt = 0
    for msg in messages:
        prompt += estimate_text_tokens(msg.get("content", "")) + 4
    completion = max(0, int(max_completion_tokens))
    return TokenEstimate(prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion)
