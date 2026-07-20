"""LLM 服务商预设（Anthropic Messages API / OpenAI Chat Completions）。"""

from dataclasses import dataclass
from typing import Literal

from core.llm.client.tool_choice import react_tool_choice_intent

LLMProtocol = Literal["anthropic", "openai"]


@dataclass(frozen=True)
class LLMProviderPreset:
    """单个服务商的连接预设。"""

    id: str
    label: str
    base_url: str
    default_model: str
    api_key_env: str  # 推荐的环境变量名
    protocol: LLMProtocol = "anthropic"


PROVIDER_PRESETS: dict[str, LLMProviderPreset] = {
    "deepseek": LLMProviderPreset(
        id="deepseek",
        label="DeepSeek",
        base_url="https://api.deepseek.com/anthropic",
        default_model="deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
        protocol="anthropic",
    ),
    "anthropic": LLMProviderPreset(
        id="anthropic",
        label="Anthropic",
        base_url="https://api.anthropic.com",
        default_model="claude-sonnet-4-20250514",
        api_key_env="ANTHROPIC_API_KEY",
        protocol="anthropic",
    ),
    "openai": LLMProviderPreset(
        id="openai",
        label="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4.1",
        api_key_env="OPENAI_API_KEY",
        protocol="openai",
    ),
    "openrouter": LLMProviderPreset(
        id="openrouter",
        label="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        default_model="anthropic/claude-sonnet-4",
        api_key_env="OPENROUTER_API_KEY",
        protocol="openai",
    ),
    "moonshot": LLMProviderPreset(
        id="moonshot",
        label="Moonshot",
        base_url="https://api.moonshot.cn/v1",
        default_model="moonshot-v1-128k",
        api_key_env="MOONSHOT_API_KEY",
        protocol="openai",
    ),
    "zhipu": LLMProviderPreset(
        id="zhipu",
        label="智谱 AI",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-4-plus",
        api_key_env="ZHIPU_API_KEY",
        protocol="openai",
    ),
    "dashscope": LLMProviderPreset(
        id="dashscope",
        label="通义千问",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-max",
        api_key_env="DASHSCOPE_API_KEY",
        protocol="openai",
    ),
}

DEFAULT_PROVIDER_ID = "deepseek"


def resolved_protocol(provider_id: str) -> LLMProtocol:
    """按 provider id 解析 wire 协议。"""
    preset = PROVIDER_PRESETS.get(provider_id)
    return preset.protocol if preset else "anthropic"


def react_tool_choice(provider_id: str) -> dict[str, str]:
    """ReAct 决策阶段的 tool_choice 意图（thinking 适配在 wire/LLMClient 层）。"""
    return react_tool_choice_intent(provider_id)


def list_providers() -> list[dict[str, str]]:
    """列出全部 LLM 服务商公开信息。"""
    return [
        {
            "id": p.id,
            "label": p.label,
            "default_model": p.default_model,
            "api_key_env": p.api_key_env,
            "protocol": p.protocol,
        }
        for p in PROVIDER_PRESETS.values()
    ]
