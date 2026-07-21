"""Agnes AI / 本地 SD 生图配置（环境变量 SVG_IMAGE_GEN_* + 运行时 PATCH）。"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

_log = logging.getLogger(__name__)

DEFAULT_AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
DEFAULT_AGNES_IMAGE_MODEL = "agnes-image-2.1-flash"
DEFAULT_OPENAI_IMAGE_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_IMAGE_MODEL = "gpt-image-1"
DEFAULT_FAL_BASE_URL = "https://fal.run"
DEFAULT_FAL_IMAGE_MODEL = "fal-ai/flux-pro/v1.1"
DEFAULT_GEMINI_IMAGE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_GEMINI_IMAGE_MODEL = "gemini-2.0-flash-preview-image-generation"
DEFAULT_SD_BASE_URL = "http://127.0.0.1:7860"
DEFAULT_IMAGE_SIZE = "1024x768"

from core.llm.tools.volcengine.ark_common import DEFAULT_ARK_BASE_URL, DEFAULT_SEEDREAM_MODEL
from core.llm.tools.shared.media_capability import list_image_provider_capabilities

IMAGE_SIZE_OPTIONS = ("1024x768", "1024x1024", "768x1024")
# 火山 SeedDream 推荐尺寸（总像素 ≥ 3686400；对齐官方 2K/4K 推荐表）
SEEDREAM_SIZE_OPTIONS = (
    "2K",
    "4K",
    "2048x2048",  # 1:1
    "2304x1728",  # 4:3
    "1728x2304",  # 3:4
    "2496x1664",  # 3:2
    "1664x2496",  # 2:3
    "2560x1440",  # 16:9
    "1440x2560",  # 9:16
    "3024x1296",  # 21:9
    "4096x4096",  # 4K 1:1
    "4704x3520",  # 4K 4:3
    "3520x4704",  # 4K 3:4
    "5504x3040",  # 4K 16:9
    "3040x5504",  # 4K 9:16
)
IMAGE_PROVIDERS = ("agnes", "local_sd", "bailian", "volcengine", "openai", "fal", "gemini")
_CUSTOM_SIZE_RE = re.compile(r"^(\d{2,5})[x×](\d{2,5})$", re.IGNORECASE)
SD_SAMPLER_OPTIONS = (
    "Euler a",
    "Euler",
    "LMS",
    "Heun",
    "DPM2",
    "DPM2 a",
    "DPM++ 2S a",
    "DPM++ 2M",
    "DPM++ SDE",
    "DPM fast",
    "DPM adaptive",
    "LMS Karras",
    "DPM2 Karras",
    "DPM2 a Karras",
    "DPM++ 2S a Karras",
    "DPM++ 2M Karras",
    "DPM++ SDE Karras",
    "DDIM",
    "PLMS",
    "UniPC",
)


def coerce_image_size(provider: str, size: str) -> str:
    """校验并规范化生图尺寸；火山支持系统预设与自定义 WxH。"""
    raw = (size or "").strip().replace("×", "x")
    if not raw:
        raise ValueError("图片尺寸不能为空")

    if provider == "volcengine":
        from core.llm.tools.image.ark_client import normalize_seedream_size

        if raw in SEEDREAM_SIZE_OPTIONS or raw in IMAGE_SIZE_OPTIONS:
            return normalize_seedream_size(raw)
        matched = _CUSTOM_SIZE_RE.fullmatch(raw)
        if not matched:
            raise ValueError(
                f"不支持的图片尺寸: {size}（请使用系统预设或自定义宽高如 2560x1440）"
            )
        w, h = int(matched.group(1)), int(matched.group(2))
        if not (64 <= w <= 8192 and 64 <= h <= 8192):
            raise ValueError("自定义宽高须在 64–8192 之间")
        ratio = w / h
        if ratio < 1 / 16 or ratio > 16:
            raise ValueError("自定义宽高比须在 1/16–16 之间")
        return normalize_seedream_size(f"{w}x{h}")

    if raw in IMAGE_SIZE_OPTIONS:
        return raw
    matched = _CUSTOM_SIZE_RE.fullmatch(raw)
    if not matched:
        raise ValueError(f"不支持的图片尺寸: {size}")
    w, h = int(matched.group(1)), int(matched.group(2))
    if not (64 <= w <= 4096 and 64 <= h <= 4096):
        raise ValueError("自定义宽高须在 64–4096 之间")
    return f"{w}x{h}"


class ImageGenSettings(BaseSettings):
    """默认使用 [Agnes AI](https://agnes-ai.com/zh-Hans/docs/overview) OpenAI 兼容生图 API。
    可通过 provider=local_sd 切换至本地 Stable Diffusion WebUI。
    """

    enabled: bool = True
    provider: str = "agnes"
    model: str = DEFAULT_AGNES_IMAGE_MODEL
    base_url: str = DEFAULT_AGNES_BASE_URL
    api_key: str | None = None
    default_size: str = DEFAULT_IMAGE_SIZE
    timeout_sec: float = 120.0
    max_concurrency: int = 4
    trust_env: bool = False
    reference_enabled: bool = True
    reference_model: str = ""
    img2img_model: str = ""
    reference_image_field: str = "image_url"

    # 本地 SD 参数
    sd_base_url: str = DEFAULT_SD_BASE_URL
    sd_steps: int = 20
    sd_cfg_scale: float = 7.0
    sd_sampler: str = "Euler a"
    sd_negative_prompt: str = ""

    # 百炼 DashScope 参数
    bailian_workspace_id: str = ""
    bailian_txt2img_model: str = "qwen-image-2.0-pro"
    bailian_img2img_model: str = "qwen-image-2.0-pro"
    fallback_provider: str = ""
    fallback_model: str = ""

    model_config = SettingsConfigDict(
        env_prefix="SVG_IMAGE_GEN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class ImageGenConfigManager:
    """生图 API 运行时配置。"""

    def __init__(self) -> None:
        self._settings = ImageGenSettings()
        self._sd_detect_result: dict[str, Any] | None = None

    def get_settings(self) -> ImageGenSettings:
        return self._settings

    @property
    def sd_detect_result(self) -> dict[str, Any] | None:
        return self._sd_detect_result

    async def detect_sd(self, force: bool = False) -> dict[str, Any]:
        """检测本地 SD 是否可用，返回检测结果 dict。"""
        if not force and self._sd_detect_result is not None:
            return self._sd_detect_result
        from core.llm.tools.image.sd_detect import detect_local_sd

        s = self._settings
        result = await detect_local_sd(s.sd_base_url)
        self._sd_detect_result = {
            "available": result.available,
            "current_model": result.current_model,
            "models": result.models,
            "error": result.error,
            "base_url": result.base_url,
        }
        return self._sd_detect_result

    def resolved_api_key(self) -> str | None:
        s = self._settings
        if s.api_key and s.api_key.strip():
            return s.api_key.strip()
        for env_name in (
            "SVG_IMAGE_GEN_API_KEY",
            "AGNES_API_KEY",
            "ARK_API_KEY",
            "OPENAI_API_KEY",
            "FAL_KEY",
            "FAL_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
        ):
            val = os.getenv(env_name)
            if val and val.strip():
                return val.strip()
        return None

    def is_available(self) -> bool:
        s = self._settings
        if not s.enabled:
            return False
        if s.provider == "local_sd":
            if self._sd_detect_result is not None:
                return bool(self._sd_detect_result.get("available"))
            return True
        if s.provider == "bailian":
            return bool(self.resolved_api_key() and s.bailian_workspace_id.strip())
        if s.provider in ("volcengine", "openai", "fal", "gemini"):
            return bool(self.resolved_api_key())
        return bool(self.resolved_api_key())

    def get_public_config(self) -> dict[str, Any]:
        s = self._settings
        sd_info = self._sd_detect_result or {}
        return {
            "enabled": s.enabled,
            "provider": s.provider,
            "provider_label": (
                "阿里云百炼" if s.provider == "bailian"
                else "火山方舟 SeedDream" if s.provider == "volcengine"
                else "OpenAI" if s.provider == "openai"
                else "fal.ai FLUX" if s.provider == "fal"
                else "Google Gemini" if s.provider == "gemini"
                else "Stable Diffusion (本地)" if s.provider == "local_sd"
                else "Agnes AI"
            ),
            "available_providers": [
                {"id": "agnes", "label": "Agnes AI"},
                {"id": "local_sd", "label": "Stable Diffusion (本地)"},
                {"id": "bailian", "label": "阿里云百炼"},
                {"id": "volcengine", "label": "火山方舟 SeedDream"},
                {"id": "openai", "label": "OpenAI GPT Image"},
                {"id": "fal", "label": "fal.ai FLUX"},
                {"id": "gemini", "label": "Google Gemini"},
            ],
            "model": s.model,
            "base_url": s.base_url,
            "default_size": s.default_size,
            "available_sizes": (
                list(SEEDREAM_SIZE_OPTIONS)
                if s.provider == "volcengine"
                else list(IMAGE_SIZE_OPTIONS)
            ),
            "timeout_sec": s.timeout_sec,
            "max_concurrency": s.max_concurrency,
            "has_api_key": bool(self.resolved_api_key()),
            "active": self.is_available(),
            "reference_enabled": s.reference_enabled,
            "reference_model": s.reference_model or s.model,
            "img2img_model": s.img2img_model or s.reference_model or s.model,
            "reference_image_field": s.reference_image_field,
            # SD 相关信息
            "sd_detected": sd_info.get("available", False),
            "sd_current_model": sd_info.get("current_model", ""),
            "sd_models": sd_info.get("models", []),
            "sd_error": sd_info.get("error", ""),
            "sd_base_url": s.sd_base_url,
            "sd_steps": s.sd_steps,
            "sd_cfg_scale": s.sd_cfg_scale,
            "sd_sampler": s.sd_sampler,
            "sd_samplers": list(SD_SAMPLER_OPTIONS),
            "sd_negative_prompt": s.sd_negative_prompt,
            # 百炼相关信息
            "bailian_workspace_id": s.bailian_workspace_id,
            "bailian_txt2img_model": s.bailian_txt2img_model,
            "bailian_img2img_model": s.bailian_img2img_model,
            "fallback_provider": s.fallback_provider,
            "fallback_model": s.fallback_model,
            "capabilities": list_image_provider_capabilities(),
        }

    def update(
        self,
        *,
        enabled: bool | None = None,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        default_size: str | None = None,
        timeout_sec: float | None = None,
        max_concurrency: int | None = None,
        reference_enabled: bool | None = None,
        reference_model: str | None = None,
        img2img_model: str | None = None,
        reference_image_field: str | None = None,
        sd_base_url: str | None = None,
        sd_steps: int | None = None,
        sd_cfg_scale: float | None = None,
        sd_sampler: str | None = None,
        sd_negative_prompt: str | None = None,
        bailian_workspace_id: str | None = None,
        bailian_txt2img_model: str | None = None,
        bailian_img2img_model: str | None = None,
        fallback_provider: str | None = None,
        fallback_model: str | None = None,
    ) -> dict[str, Any]:
        if enabled is not None:
            self._settings.enabled = enabled
        if provider is not None:
            if provider not in IMAGE_PROVIDERS:
                raise ValueError(f"不支持的生图服务商: {provider}")
            self._settings.provider = provider
            if provider == "volcengine":
                if self._settings.model in ("", DEFAULT_AGNES_IMAGE_MODEL):
                    self._settings.model = DEFAULT_SEEDREAM_MODEL
                if "agnes-ai.com" in (self._settings.base_url or ""):
                    self._settings.base_url = DEFAULT_ARK_BASE_URL
                # Agnes 小尺寸对 SeedDream 5.x 非法，自动抬到 2K
                if self._settings.default_size in IMAGE_SIZE_OPTIONS:
                    from core.llm.tools.image.ark_client import normalize_seedream_size

                    self._settings.default_size = normalize_seedream_size(
                        self._settings.default_size
                    )
            elif provider == "agnes":
                if self._settings.model == DEFAULT_SEEDREAM_MODEL:
                    self._settings.model = DEFAULT_AGNES_IMAGE_MODEL
                if "volces.com" in (self._settings.base_url or ""):
                    self._settings.base_url = DEFAULT_AGNES_BASE_URL
                if self._settings.default_size in SEEDREAM_SIZE_OPTIONS:
                    self._settings.default_size = DEFAULT_IMAGE_SIZE
            elif provider == "openai":
                if self._settings.model in ("", DEFAULT_AGNES_IMAGE_MODEL, DEFAULT_SEEDREAM_MODEL, DEFAULT_FAL_IMAGE_MODEL):
                    self._settings.model = DEFAULT_OPENAI_IMAGE_MODEL
                if not (self._settings.base_url or "").strip() or "agnes-ai.com" in self._settings.base_url or "volces.com" in self._settings.base_url:
                    self._settings.base_url = DEFAULT_OPENAI_IMAGE_BASE_URL
                if self._settings.default_size in SEEDREAM_SIZE_OPTIONS:
                    self._settings.default_size = DEFAULT_IMAGE_SIZE
            elif provider == "fal":
                if self._settings.model in ("", DEFAULT_AGNES_IMAGE_MODEL, DEFAULT_SEEDREAM_MODEL, DEFAULT_OPENAI_IMAGE_MODEL):
                    self._settings.model = DEFAULT_FAL_IMAGE_MODEL
                if not (self._settings.base_url or "").strip() or "agnes-ai.com" in (self._settings.base_url or "") or "openai.com" in (self._settings.base_url or ""):
                    self._settings.base_url = DEFAULT_FAL_BASE_URL
                if self._settings.default_size in SEEDREAM_SIZE_OPTIONS:
                    self._settings.default_size = DEFAULT_IMAGE_SIZE
            elif provider == "gemini":
                if self._settings.model in ("", DEFAULT_AGNES_IMAGE_MODEL, DEFAULT_SEEDREAM_MODEL):
                    self._settings.model = DEFAULT_GEMINI_IMAGE_MODEL
                if not (self._settings.base_url or "").strip() or "agnes-ai.com" in (self._settings.base_url or ""):
                    self._settings.base_url = DEFAULT_GEMINI_IMAGE_BASE_URL
                if self._settings.default_size in SEEDREAM_SIZE_OPTIONS:
                    self._settings.default_size = DEFAULT_IMAGE_SIZE
            # 切换 provider 时清除旧的 SD 检测结果，让下次检测重新判断
            if provider != "local_sd":
                self._sd_detect_result = None
        if model is not None:
            self._settings.model = model
        if api_key is not None:
            key = api_key.strip()
            if key:
                self._settings.api_key = key
            elif not self.resolved_api_key():
                raise ValueError("生图 API Key 不能为空")
        if base_url is not None:
            self._settings.base_url = base_url.rstrip("/")
        if default_size is not None:
            self._settings.default_size = coerce_image_size(
                self._settings.provider, default_size
            )
        if timeout_sec is not None:
            self._settings.timeout_sec = timeout_sec
        if max_concurrency is not None:
            if max_concurrency < 1:
                raise ValueError("max_concurrency 至少为 1")
            self._settings.max_concurrency = max_concurrency
        if reference_enabled is not None:
            self._settings.reference_enabled = reference_enabled
        if reference_model is not None:
            self._settings.reference_model = reference_model.strip()
        if img2img_model is not None:
            self._settings.img2img_model = img2img_model.strip()
        if reference_image_field is not None:
            field = reference_image_field.strip()
            if not field:
                raise ValueError("reference_image_field 不能为空")
            self._settings.reference_image_field = field
        # SD 参数
        if sd_base_url is not None:
            self._settings.sd_base_url = sd_base_url.rstrip("/")
            self._sd_detect_result = None  # URL 变了，清除缓存
        if sd_steps is not None:
            if sd_steps < 1 or sd_steps > 150:
                raise ValueError("sd_steps 需在 1–150 之间")
            self._settings.sd_steps = sd_steps
        if sd_cfg_scale is not None:
            if sd_cfg_scale < 1.0 or sd_cfg_scale > 30.0:
                raise ValueError("sd_cfg_scale 需在 1.0–30.0 之间")
            self._settings.sd_cfg_scale = sd_cfg_scale
        if sd_sampler is not None:
            sampler = sd_sampler.strip()
            if sampler and sampler not in SD_SAMPLER_OPTIONS:
                raise ValueError(f"不支持的采样器: {sampler}")
            self._settings.sd_sampler = sampler
        if sd_negative_prompt is not None:
            self._settings.sd_negative_prompt = sd_negative_prompt
        if bailian_workspace_id is not None:
            self._settings.bailian_workspace_id = bailian_workspace_id.strip()
        if bailian_txt2img_model is not None:
            self._settings.bailian_txt2img_model = bailian_txt2img_model.strip()
        if bailian_img2img_model is not None:
            self._settings.bailian_img2img_model = bailian_img2img_model.strip()
        if fallback_provider is not None:
            fb = fallback_provider.strip().lower()
            if fb and fb not in IMAGE_PROVIDERS:
                raise ValueError(f"不支持的 fallback 生图服务商: {fb}")
            self._settings.fallback_provider = fb
        if fallback_model is not None:
            self._settings.fallback_model = fallback_model.strip()
        return self.get_public_config()


_manager: ImageGenConfigManager | None = None


def get_image_gen_manager() -> ImageGenConfigManager:
    global _manager
    if _manager is None:
        _manager = ImageGenConfigManager()
    return _manager


def get_image_gen_settings() -> ImageGenSettings:
    return get_image_gen_manager().get_settings()


def reset_image_gen_settings() -> None:
    """测试用：重置单例。"""
    global _manager
    _manager = None


def resolved_image_gen_api_key(settings: ImageGenSettings | None = None) -> str | None:
    s = settings or get_image_gen_settings()
    if s.api_key and s.api_key.strip():
        return s.api_key.strip()
    for env_name in ("SVG_IMAGE_GEN_API_KEY", "AGNES_API_KEY"):
        val = os.getenv(env_name)
        if val and val.strip():
            return val.strip()
    return None


def is_image_gen_available(settings: ImageGenSettings | None = None) -> bool:
    s = settings or get_image_gen_settings()
    if not s.enabled:
        return False
    if s.provider == "local_sd":
        return True  # 本地 SD 不需要 API key
    if s.provider == "bailian":
        return bool(resolved_image_gen_api_key(s) and s.bailian_workspace_id.strip())
    if s.provider == "volcengine":
        return bool(resolved_image_gen_api_key(s))
    return bool(resolved_image_gen_api_key(s))
