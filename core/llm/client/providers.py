"""Anthropic Messages API 服务商预设（DeepSeek / Anthropic）。"""

from dataclasses import dataclass

from core.llm.client.tool_choice import react_tool_choice_intent


@dataclass(frozen=True)
class LLMProviderPreset:
    """单个服务商的连接预设。"""

    id: str
    label: str
    base_url: str
    default_model: str
    api_key_env: str  # 推荐的环境变量名


PROVIDER_PRESETS: dict[str, LLMProviderPreset] = {
    "deepseek": LLMProviderPreset(
        id="deepseek",
        label="DeepSeek",
        base_url="https://api.deepseek.com/anthropic",
        default_model="deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
    ),
    "anthropic": LLMProviderPreset(
        id="anthropic",
        label="Anthropic",
        base_url="https://api.anthropic.com",
        default_model="claude-sonnet-4-20250514",
        api_key_env="ANTHROPIC_API_KEY",
    ),
}

DEFAULT_PROVIDER_ID = "deepseek"


def react_tool_choice(provider_id: str) -> dict[str, str]:
    """ReAct 决策阶段的 tool_choice 意图（thinking 适配在 wire/LLMClient 层）。"""
    return react_tool_choice_intent(provider_id)


def list_providers() -> list[dict[str, str]]:
    return [
        {
            "id": p.id,
            "label": p.label,
            "default_model": p.default_model,
            "api_key_env": p.api_key_env,
        }
        for p in PROVIDER_PRESETS.values()
    ]
