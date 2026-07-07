"""图文资产生图 prompt 确定性组装。"""

from __future__ import annotations

from typing import Any

from core.models.entities import StyleConfig, TextAssetType
from core.models.image_text_asset import (
    ImageVariant,
    extract_traits,
    get_base_variant,
    normalize_image_text_content,
    parse_image_variants,
    trait_label_zh,
    variants_to_dicts,
)

PROMPT_VERSION = 1

_DEFAULT_NEGATIVE = (
    "low quality, blurry, watermark, text overlay, deformed, distorted, "
    "ugly, bad anatomy, extra limbs, cropped"
)

_SCENE_NEGATIVE = (
    "people, person, human, character, crowd, portrait, figure, "
    "silhouette of person, pedestrians"
)

_CHROMA_NEGATIVE = (
    "outdoor background, scenery, room interior, gradient background, "
    "complex background, shadows on backdrop"
)

_CHROMA_GREEN_BG = (
    "isolated subject on solid chroma key green background #00FF00, "
    "evenly lit studio, centered composition, full subject visible"
)

_STYLE_MODE_LABEL = {
    "dynamic_image": "cinematic still, suitable for Ken Burns motion",
    "ai_video": "photorealistic keyframe, video-ready composition",
}


def _type_val(asset_type: Any) -> str:
    return asset_type.value if hasattr(asset_type, "value") else str(asset_type)


def _join_parts(parts: list[str]) -> str:
    return ", ".join(p for p in parts if p and p.strip())


def _trait_lines(asset_type: Any, content: dict[str, Any]) -> list[str]:
    traits = extract_traits(asset_type, content)
    lines: list[str] = []
    for key, value in traits.items():
        val = str(value).strip()
        if not val or val == "未指定":
            continue
        lines.append(f"{trait_label_zh(key)}: {val}")
    return lines


def _compose_negative(
    asset_type: Any,
    content: dict[str, Any],
) -> str:
    """按资产类型组装 negative_prompt（尊重用户锁定）。"""
    stored_negative = str(content.get("negative_prompt", "")).strip()
    if stored_negative and content.get("prompt_locked"):
        return stored_negative
    type_val = _type_val(asset_type)
    extras: list[str] = []
    if type_val == TextAssetType.SCENE.value:
        extras.append(_SCENE_NEGATIVE)
    elif type_val in (TextAssetType.CHARACTER.value, TextAssetType.PROP.value):
        extras.append(_CHROMA_NEGATIVE)
    if stored_negative and not content.get("prompt_locked"):
        return ", ".join(p for p in [stored_negative, *extras] if p)
    if extras:
        return f"{_DEFAULT_NEGATIVE}, {', '.join(extras)}"
    return _DEFAULT_NEGATIVE


def compose_image_prompt(
    asset_type: Any,
    content: dict[str, Any],
    *,
    project_style: StyleConfig | None = None,
) -> tuple[str, str]:
    """从结构化 content 组装 base 主形象 (image_prompt, negative_prompt)。"""
    return compose_base_image_prompt(asset_type, content, project_style=project_style)


def compose_base_image_prompt(
    asset_type: Any,
    content: dict[str, Any],
    *,
    project_style: StyleConfig | None = None,
) -> tuple[str, str]:
    """设定描述 + traits → 主形象生图 prompt。"""
    type_val = _type_val(asset_type)
    desc = str(content.get("description", "")).strip()
    parts: list[str] = []

    if type_val == TextAssetType.CHARACTER.value:
        parts.append("character portrait, full body or upper body")
        parts.append(_CHROMA_GREEN_BG)
    elif type_val == TextAssetType.SCENE.value:
        parts.append(
            "empty establishing shot, scenery only, no people, "
            "no human figures, no characters"
        )
    elif type_val == TextAssetType.PROP.value:
        parts.append("object product shot, centered")
        parts.append(_CHROMA_GREEN_BG)

    if desc:
        parts.append(desc)

    trait_lines = _trait_lines(asset_type, content)
    if trait_lines:
        parts.append("; ".join(trait_lines))

    visual_style = str(content.get("visual_style", "")).strip()
    if visual_style and visual_style != "未指定":
        parts.append(f"visual style: {visual_style}")

    color_palette = str(content.get("color_palette", "")).strip()
    if color_palette and color_palette != "未指定":
        parts.append(f"color palette: {color_palette}")

    prompt_hint = str(content.get("prompt_hint", "")).strip()
    if prompt_hint and prompt_hint != "未指定":
        parts.append(prompt_hint)

    if project_style:
        parts.append(f"aspect ratio {project_style.aspect_ratio}")
        mode_label = _STYLE_MODE_LABEL.get(project_style.mode.value, "")
        if mode_label:
            parts.append(mode_label)

    tags = content.get("tags") or []
    if isinstance(tags, list):
        tag_str = ", ".join(str(t).strip() for t in tags if str(t).strip())
        if tag_str:
            parts.append(f"tags: {tag_str}")

    image_prompt = _join_parts(parts)
    negative = _compose_negative(asset_type, content)
    return image_prompt, negative


def compose_variant_image_prompt(
    asset_type: Any,
    content: dict[str, Any],
    variant: ImageVariant,
    *,
    project_style: StyleConfig | None = None,
) -> tuple[str, str]:
    """基于设定 + 变体描述组装衍生图 prompt（一致性约束）。"""
    base_prompt, negative = compose_base_image_prompt(
        asset_type, content, project_style=project_style
    )
    type_val = _type_val(asset_type)
    parts: list[str] = []
    if type_val == TextAssetType.CHARACTER.value:
        parts.append(
            "same character as reference image, keep identity costume and proportions"
        )
        parts.append(_CHROMA_GREEN_BG)
    elif type_val == TextAssetType.SCENE.value:
        parts.append(
            "same scene setting as reference, consistent style and layout, "
            "no people, scenery only"
        )
    else:
        parts.append("same object as reference, consistent design")
        parts.append(_CHROMA_GREEN_BG)

    if base_prompt:
        parts.append(f"base identity: {base_prompt[:400]}")

    vp = str(variant.variant_prompt).strip()
    if vp:
        parts.append(vp)
    meaning = str(variant.meaning).strip()
    if meaning:
        parts.append(f"context: {meaning}")
    label = str(variant.label).strip()
    if label:
        parts.append(f"variant: {label}")

    if variant.kind == "expression":
        parts.append("only change facial expression")
    elif variant.kind == "pose":
        parts.append("only change body pose and gesture")
    elif variant.kind == "action":
        parts.append("show specific action while keeping character appearance")

    image_prompt = _join_parts(parts)
    return image_prompt, negative


def apply_composed_prompts(
    asset_type: Any,
    content: dict[str, Any],
    *,
    project_style: StyleConfig | None = None,
    preserve_prompt_lock: bool = True,
    force_recompose: bool = False,
) -> dict[str, Any]:
    """写入 image_prompt / negative_prompt / prompt_version；尊重 prompt_locked。"""
    out = dict(content)
    locked = bool(out.get("prompt_locked")) and preserve_prompt_lock

    if locked and not force_recompose:
        if not out.get("prompt_version"):
            out["prompt_version"] = PROMPT_VERSION
        return out

    image_prompt, negative = compose_base_image_prompt(
        asset_type, out, project_style=project_style
    )
    out["image_prompt"] = image_prompt
    if not locked or force_recompose:
        if not str(out.get("negative_prompt", "")).strip() or force_recompose:
            out["negative_prompt"] = negative

    variants = parse_image_variants(out)
    if variants:
        base = get_base_variant(out)
        updated: list[ImageVariant] = []
        for v in variants:
            if v.kind == "base":
                if not v.prompt_locked or force_recompose:
                    v = v.model_copy(
                        update={
                            "image_prompt": image_prompt,
                        }
                    )
                updated.append(v)
            elif not v.prompt_locked or force_recompose:
                vp, _ = compose_variant_image_prompt(
                    asset_type, out, v, project_style=project_style
                )
                ref_id = v.reference_variant_id or (base.id if base else "")
                updated.append(
                    v.model_copy(
                        update={
                            "image_prompt": vp,
                            "reference_variant_id": ref_id,
                        }
                    )
                )
            else:
                updated.append(v)
        out["image_variants"] = variants_to_dicts(updated)

    out["prompt_version"] = PROMPT_VERSION
    return out


def finalize_image_text_content(
    asset_type: Any,
    raw: Any,
    *,
    project_style: StyleConfig | None = None,
    preserve_prompt_lock: bool = True,
    force_recompose: bool = False,
) -> dict[str, Any]:
    """规范化 content 并组装生图 prompt。"""
    content = normalize_image_text_content(asset_type, raw)
    return apply_composed_prompts(
        asset_type,
        content,
        project_style=project_style,
        preserve_prompt_lock=preserve_prompt_lock,
        force_recompose=force_recompose,
    )
