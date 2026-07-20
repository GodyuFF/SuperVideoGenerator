"""LLM max_tokens 上限配置测试。"""

import pytest

from core.llm.client.settings import DEFAULT_MAX_TOKENS, LLMConfigManager, MAX_OUTPUT_TOKENS


def test_max_output_tokens_constant():
    """384K 输出上限应为 393216。"""
    assert MAX_OUTPUT_TOKENS == 393_216
    assert DEFAULT_MAX_TOKENS == 8192


def test_llm_config_accepts_384k_max_tokens():
    """配置管理器应接受 384K max_tokens。"""
    mgr = LLMConfigManager()
    public = mgr.update(max_tokens=MAX_OUTPUT_TOKENS)
    assert public["max_tokens"] == MAX_OUTPUT_TOKENS


def test_llm_config_rejects_over_max_tokens():
    """超过 384K 的 max_tokens 应拒绝。"""
    mgr = LLMConfigManager()
    with pytest.raises(ValueError, match="max_tokens"):
        mgr.update(max_tokens=MAX_OUTPUT_TOKENS + 1)
