"""LLM token 预估测试。"""

from core.llm.client.token_round import TokenRoundAccumulator
from core.llm.client.tokens import (
    TokenEstimate,
    build_token_usage_meta,
    estimate_chat_tokens,
    estimate_request_breakdown,
    estimate_text_tokens,
    normalize_api_usage,
)
from core.llm.model.chat_message import chat_message
from core.llm.model.llm_request import LlmRequest


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


def test_estimate_request_breakdown_includes_pct():
    req = LlmRequest(
        system="sys",
        messages=[chat_message("user", "hi")],
    )
    bd = estimate_request_breakdown(req, 1024)
    meta = build_token_usage_meta(bd, finish_reason="end_turn")
    assert meta["breakdown"]["system"]["pct_of_total"] >= 0
    assert meta["finish_reason"] == "end_turn"


def test_normalize_api_usage_anthropic_fields():
    usage = normalize_api_usage({"input_tokens": 10, "output_tokens": 20})
    assert usage
    assert usage["prompt_tokens"] == 10
    assert usage["completion_tokens"] == 20
    assert usage["total_tokens"] == 30


def test_build_token_usage_meta_estimated_vs_actual():
    req = LlmRequest(system="sys", messages=[chat_message("user", "hi")])
    bd = estimate_request_breakdown(req, 8192)
    estimated_meta = build_token_usage_meta(bd, estimated=True)
    assert estimated_meta["estimated"] is True
    assert estimated_meta["completion_tokens"] is None
    assert estimated_meta["estimated_completion_tokens"] == 8192

    actual_meta = build_token_usage_meta(
        bd,
        estimated=False,
        actual_usage={"prompt_tokens": 100, "completion_tokens": 42, "total_tokens": 142},
    )
    assert actual_meta["estimated"] is False
    assert actual_meta["completion_tokens"] == 42
    assert actual_meta["actual_completion_tokens"] == 42


def test_token_round_accumulator_groups_by_model_and_breakdown():
    acc = TokenRoundAccumulator("conv1", "p1", "s1")
    req = LlmRequest(system="s", messages=[chat_message("user", "u")])
    bd = estimate_request_breakdown(req, 100)
    acc.add(
        "deepseek",
        "deepseek-chat",
        TokenEstimate(bd.system_tokens + bd.messages_tokens, 100, bd.total_estimated_tokens),
        breakdown=bd,
    )
    acc.add("deepseek", "deepseek-chat", TokenEstimate(50, 100, 150))
    snap = acc.snapshot()
    assert snap["total_tokens"] > 0
    assert len(snap["models"]) == 1
    assert snap["models"][0]["calls"] == 2
    assert snap["breakdown"]["system_tokens"] > 0
