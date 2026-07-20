"""从待创建资产内容构造 RAG 检索文本。"""

from __future__ import annotations

from typing import Any

from core.models.entities import TextAssetType
from core.models.image_text_asset import extract_traits, normalize_image_text_content
from core.rag.models import RagQuery


def _trait_lines(content: dict[str, Any]) -> list[str]:
    """提取 traits 键值对为可读行。"""
    traits = extract_traits(None, content)
    lines: list[str] = []
    for key, value in traits.items():
        text = str(value).strip()
        if text:
            lines.append(f"{key}: {text}")
    return lines


def build_requirement_text(
    asset_name: str,
    content: dict[str, Any],
    *,
    asset_type: TextAssetType,
) -> str:
    """拼接 name、summary、description 与 traits 为检索与 Judge 用全文。"""
    normalized = normalize_image_text_content(asset_type, content)
    parts: list[str] = [asset_name.strip()]
    for key in ("summary", "description"):
        text = str(normalized.get(key, "")).strip()
        if text:
            parts.append(text)
    parts.extend(_trait_lines(normalized))
    return "\n".join(p for p in parts if p)


def build_rag_query(
    *,
    project_id: str,
    script_id: str,
    asset_type: TextAssetType,
    asset_name: str,
    content: dict[str, Any],
) -> RagQuery:
    """构造 RAG 检索查询对象。"""
    type_val = asset_type.value
    if type_val not in ("character", "scene", "prop"):
        raise ValueError(f"RAG 不支持资产类型 {type_val}")
    requirement_text = build_requirement_text(asset_name, content, asset_type=asset_type)
    summary = str(content.get("summary", "")).strip() or asset_name.strip()
    return RagQuery(
        project_id=project_id,
        script_id=script_id,
        asset_type=type_val,  # type: ignore[arg-type]
        asset_name=asset_name.strip(),
        requirement_summary=summary,
        requirement_text=requirement_text,
    )
