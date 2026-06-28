"""LLM token 预估测试。"""

from core.llm.token_round import TokenRoundAccumulator
from core.llm.tokens import TokenEstimate, estimate_chat_tokens, estimate_text_tokens


def test_estimate_text_tokens_cjk_heavier_than_ascii():
    cjk = estimate_text_tokens("制作一段六十秒都市情感短片")
    ascii_text = estimate_text_tokens("hello world")
    assert cjk > ascii_text


def test_estimate_chat_tokens_uses_max_completion_budget():
    messages = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "写剧本"},
    ]
    est = estimate_chat_tokens(messages, max_completion_tokens=512)
    assert est.prompt_tokens > 0
    assert est.completion_tokens == 512
    assert est.total_tokens == est.prompt_tokens + 512


def test_token_round_accumulator_groups_by_model():
    acc = TokenRoundAccumulator("conv1", "p1", "s1")
    acc.add("deepseek", "deepseek-chat", TokenEstimate(100, 200, 300))
    acc.add("deepseek", "deepseek-chat", TokenEstimate(50, 100, 150))
    snap = acc.snapshot()
    assert snap["total_tokens"] == 450
    assert len(snap["models"]) == 1
    assert snap["models"][0]["calls"] == 2
    assert snap["models"][0]["total_tokens"] == 450
