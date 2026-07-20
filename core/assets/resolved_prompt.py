"""文字资产「实际生成提示词」预览：与生图/生视频路径一致的只读解析。"""

from __future__ import annotations

from typing import Any

from core.assets.image_prompt import (
    compose_base_image_prompt,
    compose_frame_image_prompt,
)
from core.assets.linked_assets_prompt import merge_prompt_with_linked_assets
from core.assets.video_prompt import compose_video_clip_prompt
from core.llm.tools.image.frames import resolve_frame_generation_prompt
from core.models.entities import TextAssetType
from core.store.memory import MemoryStore

_SUPPORTED_TYPES = frozenset(
    {
        TextAssetType.FRAME.value,
        TextAssetType.VIDEO_CLIP.value,
        TextAssetType.CHARACTER.value,
        TextAssetType.PROP.value,
        TextAssetType.SCENE.value,
    }
)


class ResolvedPromptNotFoundError(LookupError):
    """资产不存在或不属于指定项目。"""


class ResolvedPromptUnsupportedError(ValueError):
    """资产类型不支持实际生成提示词预览。"""


def _type_val(asset_type: Any) -> str:
    """将 TextAssetType 或字符串规范为 type 值。"""
    return asset_type.value if hasattr(asset_type, "value") else str(asset_type)


def build_resolved_prompt(
    store: MemoryStore,
    project_id: str,
    asset_id: str,
) -> dict[str, Any]:
    """
    解析文字资产实际生成用提示词（含关联资产动态块，不写回 content）。

    返回字段与 GET .../resolved-prompt 响应一致。
    """
    asset = store.get_text_asset(asset_id)
    if asset is None:
        raise ResolvedPromptNotFoundError(f"资产不存在：{asset_id}")
    if asset.project_id and asset.project_id != project_id:
        raise ResolvedPromptNotFoundError(f"资产不属于该项目：{asset_id}")

    type_val = _type_val(asset.type)
    if type_val not in _SUPPORTED_TYPES:
        raise ResolvedPromptUnsupportedError(
            f"类型 {type_val} 不支持实际生成提示词预览"
        )

    content = asset.content if isinstance(asset.content, dict) else {}
    authored = ""
    resolved = ""
    negative = ""
    kind = "image"

    if type_val == TextAssetType.FRAME.value:
        authored = str(content.get("image_prompt", "")).strip()
        resolved = resolve_frame_generation_prompt(store, content)
        stored_neg = str(content.get("negative_prompt", "")).strip()
        if stored_neg:
            negative = stored_neg
        else:
            _, negative = compose_frame_image_prompt(content, store=store)
        kind = "image"
    elif type_val == TextAssetType.VIDEO_CLIP.value:
        authored = str(content.get("video_prompt", "")).strip()
        resolved = compose_video_clip_prompt(content, store=store)
        negative = ""
        kind = "video"
    else:
        authored = str(content.get("image_prompt", "")).strip()
        base_prompt, base_neg = compose_base_image_prompt(asset.type, content)
        if not authored:
            authored = base_prompt
        stored_neg = str(content.get("negative_prompt", "")).strip()
        negative = stored_neg or base_neg
        resolved = merge_prompt_with_linked_assets(authored, store, content)
        kind = "image"

    differs = resolved.strip() != authored.strip()
    return {
        "asset_id": asset.id,
        "asset_type": type_val,
        "kind": kind,
        "authored_prompt": authored,
        "resolved_prompt": resolved,
        "negative_prompt": negative,
        "differs_from_authored": differs,
    }
