"""图文/漫画模式图片策略：项目配置与全局默认合并。"""

from core.llm.master.actions import uses_image_text_pipeline
from core.models.entities import ImageSourceMode, ImageTextConfig, Project, VideoStyleMode
from core.llm.client.settings import LLMConfigManager


def resolve_image_text_config(
    project: Project | None,
    llm_config: LLMConfigManager | None = None,
) -> ImageTextConfig:
    """合并项目级 image_text 与 LLM 全局默认（项目字段优先）。"""
    defaults = ImageTextConfig()
    if llm_config is not None:
        defaults = llm_config.get_image_text_defaults()
    if project is None:
        return defaults
    cfg = project.config.image_text
    return ImageTextConfig(
        source_mode=cfg.source_mode,
        image_text_preset=cfg.image_text_preset or defaults.image_text_preset,
        comic_preset=cfg.comic_preset or defaults.comic_preset,
        batch_pending_assets=cfg.batch_pending_assets,
        allow_search_fallback=cfg.allow_search_fallback,
    )


def effective_image_source(
    cfg: ImageTextConfig,
    user_choice: str | None = None,
) -> ImageSourceMode:
    """解析最终图片来源；user_choice 来自 A2UI 弹窗。"""
    if cfg.source_mode == ImageSourceMode.USER_CHOICE:
        if user_choice in (ImageSourceMode.GENERATE.value, ImageSourceMode.SEARCH.value):
            return ImageSourceMode(user_choice)
        return ImageSourceMode.GENERATE
    return cfg.source_mode


def should_prompt_image_source(cfg: ImageTextConfig, style_mode: VideoStyleMode) -> bool:
    """是否在图片步骤前弹窗让用户选择生图/搜图。"""
    return (
        uses_image_text_pipeline(style_mode)
        and cfg.source_mode == ImageSourceMode.USER_CHOICE
    )
