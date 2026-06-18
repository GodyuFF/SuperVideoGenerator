"""主流 LLM 服务商预设（OpenAI 兼容 Chat Completions）。"""

from dataclasses import dataclass


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
        base_url="https://api.deepseek.com",
        default_model="deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
    ),
    "openai": LLMProviderPreset(
        id="openai",
        label="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        api_key_env="OPENAI_API_KEY",
    ),
    "moonshot": LLMProviderPreset(
        id="moonshot",
        label="Moonshot (Kimi)",
        base_url="https://api.moonshot.cn/v1",
        default_model="moonshot-v1-8k",
        api_key_env="MOONSHOT_API_KEY",
    ),
    "zhipu": LLMProviderPreset(
        id="zhipu",
        label="智谱 AI",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-4-flash",
        api_key_env="ZHIPU_API_KEY",
    ),
    "qwen": LLMProviderPreset(
        id="qwen",
        label="通义千问",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-plus",
        api_key_env="DASHSCOPE_API_KEY",
    ),
    "anthropic": LLMProviderPreset(
        id="anthropic",
        label="Anthropic (兼容网关)",
        base_url="https://api.anthropic.com/v1",
        default_model="claude-3-5-sonnet-20241022",
        api_key_env="ANTHROPIC_API_KEY",
    ),
    "openrouter": LLMProviderPreset(
        id="openrouter",
        label="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        default_model="deepseek/deepseek-chat",
        api_key_env="OPENROUTER_API_KEY",
    ),
}

DEFAULT_PROVIDER_ID = "deepseek"


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
