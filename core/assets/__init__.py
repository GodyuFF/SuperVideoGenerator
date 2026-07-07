"""资产领域服务：图文 prompt 组装与用户 PATCH 更新。"""

from core.assets.image_prompt import (
    PROMPT_VERSION,
    apply_composed_prompts,
    compose_image_prompt,
    finalize_image_text_content,
)
from core.assets.service import patch_text_asset

__all__ = [
    "PROMPT_VERSION",
    "apply_composed_prompts",
    "compose_image_prompt",
    "finalize_image_text_content",
    "patch_text_asset",
]
