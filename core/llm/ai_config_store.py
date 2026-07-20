"""AI 配置 JSON 持久化：data/ai_config.json。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.edit.export_settings import ExportConfigManager, ExportSettings
from core.llm.client.settings import LLMConfigManager, LLMSettings
from core.llm.tools.image.settings import ImageGenConfigManager, ImageGenSettings
from core.llm.tools.tts.settings import TtsConfigManager, TtsSettings
from core.llm.tools.video.settings import VideoGenConfigManager, VideoGenSettings
from core.models.entities import ImageSourceMode
from core.rag.settings import EmbeddingConfigManager, EmbeddingSettings

DEFAULT_PATH = Path("data/ai_config.json")


def load_ai_config(path: Path | None = None) -> dict[str, Any]:
    """读取持久化配置；文件不存在或损坏时返回空 dict。"""
    target = path or DEFAULT_PATH
    if not target.exists():
        return {}
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_ai_config(data: dict[str, Any], path: Path | None = None) -> None:
    """写入持久化配置。"""
    target = path or DEFAULT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _apply_fields(settings: Any, data: dict[str, Any], *, enum_fields: dict[str, type] | None = None) -> None:
    enum_fields = enum_fields or {}
    for key, value in data.items():
        if value is None:
            continue
        if not hasattr(settings, key):
            continue
        if key in enum_fields:
            value = enum_fields[key](value)
        setattr(settings, key, value)


def apply_persisted_config(
    llm: LLMConfigManager,
    image: ImageGenConfigManager,
    video: VideoGenConfigManager,
    tts: TtsConfigManager,
    export: ExportConfigManager,
    raw: dict[str, Any],
    embedding: EmbeddingConfigManager | None = None,
) -> None:
    """用 JSON 中非空字段覆盖内存配置（JSON 优先于 .env）。"""
    llm_section = raw.get("llm")
    if isinstance(llm_section, dict):
        _apply_fields(
            llm.get_settings(),
            llm_section,
            enum_fields={"image_source_default": ImageSourceMode},
        )
        llm._normalize_provider()

    image_section = raw.get("image")
    if isinstance(image_section, dict):
        pipeline = image_section.get("pipeline")
        image_fields = {k: v for k, v in image_section.items() if k != "pipeline"}
        _apply_fields(image.get_settings(), image_fields)
        if isinstance(pipeline, dict):
            _apply_fields(
                llm.get_settings(),
                {
                    "image_source_default": pipeline.get("source_mode"),
                    "image_text_preset": pipeline.get("image_text_preset"),
                    "comic_preset": pipeline.get("comic_preset"),
                    "image_batch_pending_assets": pipeline.get("batch_pending_assets"),
                    "image_allow_search_fallback": pipeline.get("allow_search_fallback"),
                },
                enum_fields={"image_source_default": ImageSourceMode},
            )

    video_section = raw.get("video")
    if isinstance(video_section, dict):
        _apply_fields(video.get_settings(), video_section)

    tts_section = raw.get("tts")
    if isinstance(tts_section, dict):
        _apply_fields(tts.get_settings(), tts_section)

    export_section = raw.get("export")
    if isinstance(export_section, dict):
        _apply_fields(export.get_settings(), export_section)

    embedding_section = raw.get("embedding")
    if embedding is not None and isinstance(embedding_section, dict):
        _apply_fields(embedding.get_settings(), embedding_section)


def _settings_dict(settings: Any, fields: list[str]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for field in fields:
        if hasattr(settings, field):
            val = getattr(settings, field)
            if hasattr(val, "value"):
                val = val.value
            data[field] = val
    return data


def collect_persisted_config(
    llm: LLMConfigManager,
    image: ImageGenConfigManager,
    video: VideoGenConfigManager,
    tts: TtsConfigManager,
    export: ExportConfigManager,
    embedding: EmbeddingConfigManager | None = None,
) -> dict[str, Any]:
    """从各 ConfigManager 收集可持久化字段。"""
    ls: LLMSettings = llm.get_settings()
    pipeline = llm.get_image_text_defaults()
    es: ExportSettings = export.get_settings()
    data: dict[str, Any] = {
        "llm": {
            **_settings_dict(
                ls,
                [
                    "provider",
                    "model",
                    "api_key",
                    "base_url",
                    "temperature",
                    "max_tokens",
                    "context_window_tokens",
                    "history_keep_messages",
                    "timeout_sec",
                    "use_llm_react",
                    "show_react_details",
                    "trust_env",
                    "image_source_default",
                    "image_text_preset",
                    "comic_preset",
                    "image_batch_pending_assets",
                    "image_allow_search_fallback",
                ],
            ),
        },
        "image": {
            **_settings_dict(
                image.get_settings(),
                [
                    "enabled",
                    "provider",
                    "model",
                    "api_key",
                    "base_url",
                    "default_size",
                    "timeout_sec",
                    "max_concurrency",
                    "trust_env",
                    "sd_base_url",
                    "sd_steps",
                    "sd_cfg_scale",
                    "sd_sampler",
                    "sd_negative_prompt",
                    "bailian_workspace_id",
                    "bailian_txt2img_model",
                    "bailian_img2img_model",
                    "reference_enabled",
                    "reference_model",
                    "img2img_model",
                    "fallback_provider",
                    "fallback_model",
                ],
            ),
            "pipeline": pipeline.model_dump(),
        },
        "video": _settings_dict(
            video.get_settings(),
            [
                "enabled",
                "provider",
                "model",
                "api_key",
                "base_url",
                "max_duration_sec",
                "resolution",
                "timeout_sec",
                "poll_interval_sec",
                "create_min_interval_sec",
                "create_max_attempts",
                "max_concurrency",
                "trust_env",
                "fallback_provider",
                "fallback_model",
            ],
        ),
        "tts": _settings_dict(
            tts.get_settings(),
            [
                "enabled",
                "provider",
                "model",
                "api_key",
                "base_url",
                "default_language",
                "default_voice",
                "voice_rate",
                "voice_volume",
                "sample_rate",
                "timeout_sec",
                "edge_tts_timeout_sec",
                "max_concurrency",
                "ffmpeg_path",
                "gemini_api_key",
                "mimo_api_key",
                "mimo_base_url",
                "mimo_tts_model",
                "mimo_style_prompt",
                "siliconflow_api_key",
                "azure_speech_key",
                "azure_speech_region",
                "trust_env",
            ],
        ),
        "export": _settings_dict(
            es,
            [
                "enabled",
                "ffmpeg_path",
                "fps",
                "width",
                "height",
                "crf",
            ],
        ),
    }
    if embedding is not None:
        es_emb: EmbeddingSettings = embedding.get_settings()
        data["embedding"] = _settings_dict(
            es_emb,
            ["enabled", "api_key", "base_url", "model"],
        )
    return data
