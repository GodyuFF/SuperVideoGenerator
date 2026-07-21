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
    trait_label,
    trait_label_zh,
    variants_to_dicts,
)

PROMPT_VERSION = 2

_DEFAULT_NEGATIVE = (
    "low quality, blurry, watermark, text overlay, deformed, distorted, "
    "ugly, bad anatomy, extra limbs, cropped"
)

_SCENE_POSITIVE_PREFIX = (
    "environment background plate, matte backdrop, empty location, no subjects, "
    "no story action, no characters, no props as focal subjects, "
    "background layer only, scenery only"
)

_SCENE_NEGATIVE = (
    "people, person, human, character, crowd, portrait, figure, "
    "silhouette of person, pedestrians, generated characters, props as subjects, "
    "human silhouettes, green screen, chroma key residue, watermark, "
    "animal, pet, face, hands, body, action scene, narrative scene, "
    "main subject, product shot, handheld object, pedestrian, "
    "vehicle interior with driver"
)

_FRAME_NEGATIVE = (
    "green screen, chroma key, watermark, extra people, duplicate characters, "
    "wrong scene layout, cropped subjects, text overlay"
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
    "storybook": "cinematic still, suitable for Ken Burns motion",
    "ai_video": "photorealistic keyframe, video-ready composition",
}


def _type_val(asset_type: Any) -> str:
    return asset_type.value if hasattr(asset_type, "value") else str(asset_type)


def _join_parts(parts: list[str]) -> str:
    return ", ".join(p for p in parts if p and p.strip())


def _trait_lines(asset_type: Any, content: dict[str, Any], *, language: str = "zh") -> list[str]:
    type_val = _type_val(asset_type)
    if type_val == TextAssetType.SCENE.value:
        return _scene_trait_lines(content, language=language)
    traits = extract_traits(asset_type, content)
    lines: list[str] = []
    for key, value in traits.items():
        val = str(value).strip()
        if not val or val == "未指定":
            continue
        lines.append(f"{trait_label(key, language)}: {val}")
    return lines


_SCENE_TRAIT_SUFFIX: dict[str, str] = {
    "key_objects": "environment fixed fixtures only, not standalone prop assets",
    "foreground": "scenery only, no figures",
    "background": "scenery only, no figures",
}


def _scene_trait_lines(content: dict[str, Any], *, language: str = "zh") -> list[str]:
    traits = extract_traits(TextAssetType.SCENE, content)
    lines: list[str] = []
    for key, value in traits.items():
        val = str(value).strip()
        if not val or val == "未指定":
            continue
        label = trait_label(key, language)
        suffix = _SCENE_TRAIT_SUFFIX.get(key)
        if suffix:
            lines.append(f"{label} ({suffix}): {val}")
        else:
            lines.append(f"{label}: {val}")
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
    language: str = "zh",
) -> tuple[str, str]:
    """从结构化 content 组装 base 主形象 (image_prompt, negative_prompt)。"""
    return compose_base_image_prompt(asset_type, content, project_style=project_style, language=language)


def compose_base_image_prompt(
    asset_type: Any,
    content: dict[str, Any],
    *,
    project_style: StyleConfig | None = None,
    language: str = "zh",
) -> tuple[str, str]:
    """设定描述 + traits → 主形象生图 prompt。language: 'zh' | 'en'。"""
    type_val = _type_val(asset_type)
    desc = str(content.get("description", "")).strip()
    parts: list[str] = []

    if type_val == TextAssetType.CHARACTER.value:
        parts.append("character portrait, full body or upper body")
        parts.append(_CHROMA_GREEN_BG)
    elif type_val == TextAssetType.SCENE.value:
        parts.append(_SCENE_POSITIVE_PREFIX)
    elif type_val == TextAssetType.PROP.value:
        parts.append("object product shot, centered")
        parts.append(_CHROMA_GREEN_BG)

    if desc:
        parts.append(desc)

    trait_lines = _trait_lines(asset_type, content, language=language)
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
        mode_key = (
            project_style.mode.value
            if hasattr(project_style.mode, "value")
            else str(project_style.mode)
        )
        mode_label = _STYLE_MODE_LABEL.get(mode_key, "")
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


def compose_frame_image_prompt(
    content: dict[str, Any],
    *,
    store: Any | None = None,
    project_style: StyleConfig | None = None,
) -> tuple[str, str]:
    """画面（frame）多参考图合成 prompt；主文案以 image_prompt 为准（notes 不参与）。"""
    parts: list[str] = [
        "composite cinematic frame, full scene composition",
        "preserve scene layout and background from first reference image",
    ]
    summary = str(content.get("summary", "")).strip()
    if summary:
        parts.append(f"summary: {summary}")
    # 规范字段：image_prompt；旧数据可能仅有 description / composition_prompt
    authored = str(content.get("image_prompt", "")).strip()
    if not authored:
        authored = str(content.get("description", "")).strip()
    if authored:
        parts.append(authored)
    legacy_comp = str(content.get("composition_prompt", "")).strip()
    if legacy_comp and legacy_comp not in authored:
        parts.append(legacy_comp)

    if project_style:
        parts.append(f"aspect ratio {project_style.aspect_ratio}")
        mode_key = (
            project_style.mode.value
            if hasattr(project_style.mode, "value")
            else str(project_style.mode)
        )
        mode_label = _STYLE_MODE_LABEL.get(mode_key, "")
        if mode_label:
            parts.append(mode_label)

    # 先拼正向正文，再由 merge 置顶【参考图说明】（勿把分区块塞进 _join_parts）
    image_prompt = _join_parts(parts)
    if store is not None:
        from core.assets.linked_assets_prompt import merge_prompt_with_linked_assets

        image_prompt = merge_prompt_with_linked_assets(image_prompt, store, content)
    negative = f"{_DEFAULT_NEGATIVE}, {_FRAME_NEGATIVE}"
    return image_prompt, negative


def compose_variant_image_prompt(
    asset_type: Any,
    content: dict[str, Any],
    variant: ImageVariant,
    *,
    project_style: StyleConfig | None = None,
    language: str = "zh",
) -> tuple[str, str]:
    """基于设定 + 变体描述组装衍生图 prompt（一致性约束）。"""
    base_prompt, negative = compose_base_image_prompt(
        asset_type, content, project_style=project_style, language=language
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
            "empty background plate, same layout and style as reference, "
            "no people, no prop subjects, scenery only"
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


def recompose_variant_image_prompts(
    asset_type: Any,
    content: dict[str, Any],
    *,
    project_style: StyleConfig | None = None,
    language: str = "zh",
) -> dict[str, Any]:
    """仅重算 image_variants 的 image_prompt，不改动资产级主 prompt。"""
    out = dict(content)
    variants = parse_image_variants(out)
    if not variants:
        return out
    base = get_base_variant(out)
    base_prompt, _ = compose_base_image_prompt(
        asset_type, out, project_style=project_style, language=language
    )
    updated: list[ImageVariant] = []
    for v in variants:
        if v.prompt_locked:
            updated.append(v)
            continue
        if v.kind == "base":
            updated.append(v.model_copy(update={"image_prompt": base_prompt}))
            continue
        vp, _ = compose_variant_image_prompt(
            asset_type, out, v, project_style=project_style, language=language
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
    out["image_variants"] = variants_to_dicts(updated)
    return out


def apply_composed_prompts(
    asset_type: Any,
    content: dict[str, Any],
    *,
    project_style: StyleConfig | None = None,
    preserve_prompt_lock: bool = True,
    force_recompose: bool = False,
    language: str = "zh",
) -> dict[str, Any]:
    """写入 image_prompt / negative_prompt / prompt_version；尊重 prompt_locked。"""
    out = dict(content)
    locked = bool(out.get("prompt_locked")) and preserve_prompt_lock

    if locked and not force_recompose:
        if not out.get("prompt_version"):
            out["prompt_version"] = PROMPT_VERSION
        return out

    type_val = _type_val(asset_type)
    if type_val == TextAssetType.FRAME.value:
        image_prompt, negative = compose_frame_image_prompt(
            out, project_style=project_style
        )
        out["image_prompt"] = image_prompt
        if not locked or force_recompose:
            if not str(out.get("negative_prompt", "")).strip() or force_recompose:
                out["negative_prompt"] = negative
        out["prompt_version"] = PROMPT_VERSION
        return out

    image_prompt, negative = compose_base_image_prompt(
        asset_type, out, project_style=project_style, language=language
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
                    asset_type, out, v, project_style=project_style, language=language
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
    language: str = "zh",
) -> dict[str, Any]:
    """规范化 content 并组装生图 prompt。"""
    content = normalize_image_text_content(asset_type, raw)
    return apply_composed_prompts(
        asset_type,
        content,
        project_style=project_style,
        preserve_prompt_lock=preserve_prompt_lock,
        force_recompose=force_recompose,
        language=language,
    )
