"""统一 AI 配置：LLM / 图片 / 视频 / TTS / 剪辑导出 / Embedding。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.edit.export_settings import ExportConfigManager, get_export_manager
from core.llm.ai_config_store import (
    DEFAULT_PATH,
    apply_persisted_config,
    collect_persisted_config,
    load_ai_config,
    save_ai_config,
)
from core.llm.client.settings import LLMConfigManager
from core.llm.tools.image.settings import ImageGenConfigManager, get_image_gen_manager
from core.llm.tools.tts.settings import TtsConfigManager, get_tts_manager
from core.llm.tools.video.settings import VideoGenConfigManager, get_video_gen_manager
from core.models.entities import ImageSourceMode
from core.rag.settings import EmbeddingConfigManager, get_embedding_manager


class AiConfigManager:
    """聚合各 AI 能力配置，供 /api/ai/config 与前端 AI 配置页使用。"""

    def __init__(
        self,
        llm: LLMConfigManager | None = None,
        image: ImageGenConfigManager | None = None,
        video: VideoGenConfigManager | None = None,
        tts: TtsConfigManager | None = None,
        export: ExportConfigManager | None = None,
        embedding: EmbeddingConfigManager | None = None,
        *,
        path: Path | None = None,
    ) -> None:
        self._path = path or DEFAULT_PATH
        self._llm = llm or LLMConfigManager()
        self._image = image or get_image_gen_manager()
        self._video = video or get_video_gen_manager()
        self._tts = tts or get_tts_manager()
        self._export = export or get_export_manager()
        self._embedding = embedding or get_embedding_manager()
        persisted = load_ai_config(self._path)
        if persisted:
            apply_persisted_config(
                self._llm,
                self._image,
                self._video,
                self._tts,
                self._export,
                persisted,
                embedding=self._embedding,
            )

    def _persist(self) -> None:
        save_ai_config(
            collect_persisted_config(
                self._llm,
                self._image,
                self._video,
                self._tts,
                self._export,
                embedding=self._embedding,
            ),
            self._path,
        )

    @property
    def llm(self) -> LLMConfigManager:
        return self._llm

    @property
    def image(self) -> ImageGenConfigManager:
        return self._image

    @property
    def video(self) -> VideoGenConfigManager:
        return self._video

    @property
    def tts(self) -> TtsConfigManager:
        return self._tts

    @property
    def export(self) -> ExportConfigManager:
        return self._export

    @property
    def embedding(self) -> EmbeddingConfigManager:
        return self._embedding

    def get_public_config(self) -> dict[str, Any]:
        llm_public = self._llm.get_public_config()
        llm_section = {
            k: v
            for k, v in llm_public.items()
            if k not in ("image_text_defaults", "image_gen")
        }
        return {
            "llm": llm_section,
            "image": {
                **self._image.get_public_config(),
                "pipeline": self._llm.get_image_text_defaults().model_dump(),
            },
            "video": self._video.get_public_config(),
            "tts": self._tts.get_public_config(),
            "export": self._export.get_public_config(),
            "embedding": self._embedding.get_public_config(),
        }

    def update(
        self,
        *,
        llm: dict[str, Any] | None = None,
        image: dict[str, Any] | None = None,
        video: dict[str, Any] | None = None,
        tts: dict[str, Any] | None = None,
        export: dict[str, Any] | None = None,
        embedding: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if llm:
            self._llm.update(
                provider=llm.get("provider"),
                model=llm.get("model"),
                api_key=llm.get("api_key"),
                base_url=llm.get("base_url"),
                use_llm_react=llm.get("use_llm_react"),
                show_react_details=llm.get("show_react_details"),
                temperature=llm.get("temperature"),
                max_tokens=llm.get("max_tokens"),
                context_window_tokens=llm.get("context_window_tokens"),
                history_keep_messages=llm.get("history_keep_messages"),
            )
        if image:
            pipeline = image.get("pipeline")
            if isinstance(pipeline, dict):
                source_mode = pipeline.get("source_mode")
                if source_mode is not None and not isinstance(source_mode, ImageSourceMode):
                    source_mode = ImageSourceMode(source_mode)
                self._llm.update(
                    image_source_default=source_mode,
                    image_text_preset=pipeline.get("image_text_preset"),
                    comic_preset=pipeline.get("comic_preset"),
                    image_batch_pending_assets=pipeline.get("batch_pending_assets"),
                    image_allow_search_fallback=pipeline.get("allow_search_fallback"),
                )
            self._image.update(
                enabled=image.get("enabled"),
                provider=image.get("provider"),
                model=image.get("model"),
                api_key=image.get("api_key"),
                base_url=image.get("base_url"),
                default_size=image.get("default_size"),
                timeout_sec=image.get("timeout_sec"),
                sd_base_url=image.get("sd_base_url"),
                sd_steps=image.get("sd_steps"),
                sd_cfg_scale=image.get("sd_cfg_scale"),
                sd_sampler=image.get("sd_sampler"),
                sd_negative_prompt=image.get("sd_negative_prompt"),
                bailian_workspace_id=image.get("bailian_workspace_id"),
                bailian_txt2img_model=image.get("bailian_txt2img_model"),
                bailian_img2img_model=image.get("bailian_img2img_model"),
            )
        if video:
            self._video.update(
                enabled=video.get("enabled"),
                provider=video.get("provider"),
                model=video.get("model"),
                api_key=video.get("api_key"),
                base_url=video.get("base_url"),
                max_duration_sec=video.get("max_duration_sec"),
                resolution=video.get("resolution"),
                timeout_sec=video.get("timeout_sec"),
                poll_interval_sec=video.get("poll_interval_sec"),
                create_min_interval_sec=video.get("create_min_interval_sec"),
                create_max_attempts=video.get("create_max_attempts"),
                max_concurrency=video.get("max_concurrency"),
            )
        if tts:
            self._tts.update(
                enabled=tts.get("enabled"),
                provider=tts.get("provider"),
                model=tts.get("model"),
                api_key=tts.get("api_key"),
                base_url=tts.get("base_url"),
                default_language=tts.get("default_language"),
                default_voice=tts.get("default_voice"),
                voice_rate=tts.get("voice_rate"),
                voice_volume=tts.get("voice_volume"),
                sample_rate=tts.get("sample_rate"),
                timeout_sec=tts.get("timeout_sec"),
                edge_tts_timeout_sec=tts.get("edge_tts_timeout_sec"),
                max_concurrency=tts.get("max_concurrency"),
                ffmpeg_path=tts.get("ffmpeg_path"),
                gemini_api_key=tts.get("gemini_api_key"),
                mimo_api_key=tts.get("mimo_api_key"),
                mimo_base_url=tts.get("mimo_base_url"),
                mimo_tts_model=tts.get("mimo_tts_model"),
                mimo_style_prompt=tts.get("mimo_style_prompt"),
                siliconflow_api_key=tts.get("siliconflow_api_key"),
                azure_speech_key=tts.get("azure_speech_key"),
                azure_speech_region=tts.get("azure_speech_region"),
            )
        if export:
            self._export.update(
                enabled=export.get("enabled"),
                ffmpeg_path=export.get("ffmpeg_path"),
                fps=export.get("fps"),
                width=export.get("width"),
                height=export.get("height"),
                crf=export.get("crf"),
            )
        if embedding:
            self._embedding.update(
                enabled=embedding.get("enabled"),
                api_key=embedding.get("api_key"),
                base_url=embedding.get("base_url"),
                model=embedding.get("model"),
            )
        self._persist()
        return self.get_public_config()
