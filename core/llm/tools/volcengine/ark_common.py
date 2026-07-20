"""火山方舟 API 公共常量与鉴权。"""

from __future__ import annotations

import os

DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_SEEDREAM_MODEL = "doubao-seedream-5-0-pro"
DEFAULT_SEEDANCE_MODEL = "doubao-seedance-2-0"


def resolve_ark_api_key(
    explicit_key: str | None = None,
    *,
    env_names: tuple[str, ...] = ("SVG_IMAGE_GEN_API_KEY", "ARK_API_KEY"),
) -> str:
    """解析火山方舟 API Key：显式配置 > 环境变量。"""
    key = str(explicit_key or "").strip()
    if key:
        return key
    for name in env_names:
        val = os.getenv(name, "").strip()
        if val:
            return val
    raise ValueError("未配置火山方舟 API Key（ARK_API_KEY 或 SVG_*_GEN_API_KEY）")


def ark_auth_headers(api_key: str) -> dict[str, str]:
    """构建 Bearer 鉴权头。"""
    return {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "Accept-Encoding": "identity",
    }


def normalize_ark_base_url(base_url: str) -> str:
    """规范化 base_url，确保以 /api/v3 结尾。"""
    root = str(base_url or DEFAULT_ARK_BASE_URL).strip().rstrip("/")
    if not root:
        return DEFAULT_ARK_BASE_URL
    if root.endswith("/api/v3"):
        return root
    if root.endswith("/v3"):
        return root
    if root.endswith("/api"):
        return f"{root}/v3"
    return f"{root}/api/v3"
