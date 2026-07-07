"""搜图后文字资产回写：白名单自动 patch 与重大变更检测。"""

from __future__ import annotations

from typing import Any

from core.assets.image_prompt import compose_image_prompt
from core.models.entities import MediaAssetType, TextAsset
from core.models.image_text_asset import is_image_text_asset, normalize_image_text_content

# 可自动 patch 的安全字段（不含语义主文案）
AUTO_PATCH_FIELDS = frozenset(
    {
        "color_palette",
        "visual_style",
        "prompt_hint",
        "display_mode",
        "negative_prompt",
    }
)

MAJOR_FIELDS = frozenset({"summary", "description", "text"})

# 仅搜图配图需从实际图片反推视觉字段；生图模型产出已由 prompt 确定
_GENERATED_IMAGE_SOURCES = frozenset({"agnes", "generate", "generated", "ai"})


def image_media_source(media: Any) -> str:
    if media is None:
        return ""
    meta = getattr(media, "metadata", None) or {}
    if not isinstance(meta, dict):
        return ""
    return str(meta.get("source", "")).strip().lower()


def needs_sync_from_image(store: Any, asset: TextAsset) -> tuple[bool, str]:
    """
    判断是否应对该文字资产执行 sync_text_from_image。
    返回 (needs_sync, reason_if_skipped)。
    """
    media_id = asset.primary_media_id
    if not media_id:
        for ref in store.list_references_from(asset.id):
            target = store.media_assets.get(ref.target_id)
            if target and target.type == MediaAssetType.IMAGE:
                media_id = target.id
                break
    if not media_id:
        return False, "无关联图片"
    media = store.media_assets.get(media_id)
    if media is None:
        return False, "关联图片不存在"
    source = image_media_source(media)
    if source in _GENERATED_IMAGE_SOURCES or source.startswith("agnes"):
        return False, "图片由生图模型生成，文字资产已由 prompt 确定"
    if source == "search":
        return True, ""
    # 未知来源：保守起见允许 sync（兼容旧数据）
    if source:
        return True, ""
    return True, ""


def split_image_observations(
    observations: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """
    将 image_observations 拆为 auto_patch、major_proposed、major_field_names。
    """
    auto: dict[str, Any] = {}
    major: dict[str, Any] = {}
    major_names: list[str] = []
    for key, val in observations.items():
        if key in AUTO_PATCH_FIELDS and val is not None and str(val).strip():
            auto[key] = val
        elif key in MAJOR_FIELDS and val is not None and str(val).strip():
            major[key] = val
            major_names.append(key)
    return auto, major, major_names


def apply_auto_patch_to_content(
    asset_type: Any,
    content: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    """合并白名单字段；negative_prompt 追加而非覆盖。"""
    merged = dict(content)
    for key, val in patch.items():
        if key not in AUTO_PATCH_FIELDS:
            continue
        if key == "negative_prompt":
            existing = str(merged.get("negative_prompt", "")).strip()
            incoming = str(val).strip()
            if incoming and incoming not in existing:
                merged["negative_prompt"] = f"{existing}, {incoming}".strip(", ")
        else:
            merged[key] = val
    if is_image_text_asset(asset_type):
        merged = normalize_image_text_content(asset_type, merged)
        image_prompt, _negative = compose_image_prompt(asset_type, merged)
        merged["image_prompt"] = image_prompt
    return merged


def build_sync_summary(
    asset: TextAsset,
    auto_patch: dict[str, Any],
    major_fields: list[str],
    *,
    applied_major: bool = False,
) -> str:
    parts = [f"已同步文字资产 {asset.name}（{asset.id}）"]
    if auto_patch:
        parts.append(f"自动更新字段：{', '.join(sorted(auto_patch.keys()))}")
    if major_fields:
        if applied_major:
            parts.append(f"已应用重大变更：{', '.join(major_fields)}")
        else:
            parts.append(
                f"待确认重大变更字段：{', '.join(major_fields)}（请 update_* 或用户确认）"
            )
    return "；".join(parts)
