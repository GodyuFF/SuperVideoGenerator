"""网页读取配置（环境变量 SVG_WEB_FETCH_*）。"""

from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class WebFetchSettings(BaseSettings):
    timeout_sec: float = 30.0
    max_bytes: int = 2_000_000
    max_chars_default: int = 8000
    user_agent: str = _DEFAULT_UA
    accept_language: str = "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    warmup_domain: bool = True
    use_jina_fallback: bool = True
    jina_reader_base: str = "https://r.jina.ai/"

    model_config = SettingsConfigDict(
        env_prefix="SVG_WEB_FETCH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


_settings: WebFetchSettings | None = None


def get_web_fetch_settings() -> WebFetchSettings:
    global _settings
    if _settings is None:
        _settings = WebFetchSettings()
    return _settings
