"""SD 生图纯英文提示词重组装 —— 将中文 trait 值与描述转换为英文关键词。"""

from __future__ import annotations

import re
from typing import Any

from core.assets.image_prompt import (
    _CHROMA_GREEN_BG,
    _SCENE_POSITIVE_PREFIX,
    _join_parts,
    compose_frame_image_prompt,
)
from core.models.image_text_asset import (
    extract_traits,
    find_variant,
    is_image_text_asset,
    normalize_image_text_content,
    trait_label,
)
from core.store.memory import MemoryStore

# ---- 中文 → 英文颜色/材质词映射 ----
_COLOR_CN_EN: dict[str, str] = {
    "粉色": "pink", "粉红": "pink", "粉": "pink",
    "红色": "red", "红": "red",
    "蓝色": "blue", "蓝": "blue",
    "绿色": "green", "绿": "green",
    "黄色": "yellow", "黄": "yellow",
    "紫色": "purple", "紫": "purple",
    "橙色": "orange", "橙": "orange",
    "白色": "white", "白": "white",
    "黑色": "black", "黑": "black",
    "灰色": "gray", "灰": "gray", "浅灰": "light gray",
    "金色": "gold", "金": "gold",
    "银色": "silver", "银": "silver",
    "棕色": "brown",
    "深": "dark", "浅": "light", "亮": "bright",
    "柔和": "soft", "温柔": "soft",
    "暖": "warm", "冷": "cool",
    "色调": "tone", "主调": "dominant",
}

# 常见中文 trait 值 → 英文
_TRAIT_VALUE_CN_EN: dict[str, dict[str, str]] = {
    "gender": {"雄性": "male", "雌性": "female", "男": "male", "女": "female"},
    "age_range": {
        "幼年": "young", "少年": "teen", "青年": "young adult",
        "成年": "adult", "中年": "middle-aged", "老年": "elderly",
    },
    "body_type": {
        "矮胖圆滚": "chubby round", "矮胖": "short chubby",
        "圆胖敦实": "round stocky", "圆滚": "round",
        "瘦高": "tall slim", "苗条": "slim",
        "标准": "average", "健壮": "muscular",
    },
}


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[一-鿿]", text))


def _extract_english(text: str) -> str:
    """从文本中提取英文部分；若全是英文则直接返回。"""
    if not text or text == "未指定":
        return ""
    if not _has_cjk(text):
        return text.strip()
    parts = []
    for part in text.split(","):
        part = part.strip()
        if part and not _has_cjk(part):
            parts.append(part)
    return ", ".join(parts) if parts else ""


def _translate_color_text(text: str) -> str:
    """替换颜色/材质相关的中文词为英文。"""
    if not text or not _has_cjk(text):
        return text
    result = text
    for cn, en in _COLOR_CN_EN.items():
        result = result.replace(cn, f" {en} ")
    result = re.sub(r"\s+", " ", result).strip()
    if _has_cjk(result):
        words = result.split()
        en_words = [w for w in words if not _has_cjk(w)]
        result = " ".join(en_words)
    return result


def _translate_trait_value(key: str, value: str) -> str:
    """将 trait 值尽可能转为英文关键词。"""
    val = value.strip()
    if not val or val == "未指定":
        return ""

    # 已有精确映射
    mapping = _TRAIT_VALUE_CN_EN.get(key)
    if isinstance(mapping, dict):
        for cn, en in mapping.items():
            if cn in val:
                return en
        return ""

    # 颜色类
    if key in ("eye_color", "hair_color", "color", "color_tone"):
        return _translate_color_text(val)

    # 值较短则尝试颜色翻译
    if len(val) <= 6:
        translated = _translate_color_text(val)
        if translated and not _has_cjk(translated):
            return translated

    return ""


def _extract_keywords_from_text(text: str, max_len: int = 200) -> str:
    """从文本中提取英文关键词；无英文则返回空。"""
    if not text or text == "未指定":
        return ""
    if not _has_cjk(text):
        return text.strip()[:max_len]
    en = _extract_english(text)
    if en:
        return en[:max_len]
    # 中文太长的跳过（SD 无法理解）
    return ""


def _build_base_identity_parts(
    asset_type_val: str,
    content: dict[str, Any],
) -> list[str]:
    """构建 base identity 的英文部分（用于 variant 的 base identity 字段）。"""
    parts: list[str] = []

    # 英文类型前缀
    if asset_type_val == "character":
        parts.append("character portrait, full body or upper body")
        parts.append(_CHROMA_GREEN_BG)
    elif asset_type_val == "scene":
        parts.append(_SCENE_POSITIVE_PREFIX)
    elif asset_type_val == "prop":
        parts.append("object product shot, centered")
        parts.append(_CHROMA_GREEN_BG)

    # Description (英文提取)
    desc = str(content.get("description", "")).strip()
    desc_en = _extract_keywords_from_text(desc)
    if desc_en:
        parts.append(desc_en)

    # Visual style
    vs = str(content.get("visual_style", "")).strip()
    vs_en = _extract_english(vs)
    if vs_en:
        parts.append(f"visual style: {vs_en}")

    # Color palette
    cp = str(content.get("color_palette", "")).strip()
    cp_en = _translate_color_text(cp) if _has_cjk(cp) else cp
    if cp_en:
        parts.append(f"color palette: {cp_en}")

    # Traits
    trait_parts: list[str] = []
    traits = extract_traits(asset_type_val, content)
    for key, value in traits.items():
        val = str(value).strip()
        if not val or val == "未指定":
            continue
        en_val = _translate_trait_value(key, val)
        if en_val:
            label = trait_label(key, "en")
            trait_parts.append(f"{label}: {en_val}")
    if trait_parts:
        parts.append("; ".join(trait_parts))

    return parts


def _build_chroma_green_bg() -> str:
    return (
        "isolated subject on solid chroma key green background #00FF00, "
        "evenly lit studio, centered composition, full subject visible"
    )


def recompose_prompt_in_english(
    store: MemoryStore,
    item: dict[str, Any],
) -> str:
    """为本地 SD 重新组装纯英文提示词。

    - trait 标签 → 英文
    - trait 值 → 英文（有映射时）
    - description/visual_style → 提取英文部分或翻译颜色词
    - variant_prompt/meaning/label → 英文提取
    - 添加 SD 质量关键词
    """
    source_id = str(item.get("source_text_asset_id", "")).strip()
    variant_id = str(item.get("variant_id", "")).strip()
    src = store.get_text_asset(source_id)
    if not src or not is_image_text_asset(src.type):
        return ""

    content = normalize_image_text_content(src.type, src.content)

    # Frame: 用 compose_frame_image_prompt（模板已是英文）
    if src.type.value == "frame":
        prompt, _ = compose_frame_image_prompt(content, store=store)
        return prompt

    is_variant = bool(variant_id)
    variant = find_variant(content, variant_id) if is_variant else None

    # ---- 组装 ----
    parts: list[str] = []

    # 英文前缀（根据类型）
    if is_variant and variant and variant.kind != "base":
        # Variant 一致性约束
        if src.type.value == "character":
            parts.append(
                "same character as reference image, "
                "keep identity costume and proportions"
            )
            parts.append(_CHROMA_GREEN_BG)
        elif src.type.value == "scene":
            parts.append(
                "empty background plate, same layout and style as reference, "
                "no people, no prop subjects, scenery only"
            )
        else:
            parts.append("same object as reference, consistent design")
            parts.append(_CHROMA_GREEN_BG)
    elif src.type.value == "character":
        parts.append("character portrait, full body or upper body")
        parts.append(_CHROMA_GREEN_BG)
    elif src.type.value == "scene":
        parts.append(_SCENE_POSITIVE_PREFIX)
    elif src.type.value == "prop":
        parts.append("object product shot, centered")
        parts.append(_CHROMA_GREEN_BG)

    # 名称（仅当是英文时）
    name = src.name.strip()
    if name and not _has_cjk(name):
        parts.append(name)

    # Description: 提取英文部分
    if is_variant and variant and variant.kind != "base":
        # variant 场景下 base identity 使用净化后的 base prompt
        # 单独构建 base 部分（不调用 compose，避免中文内容混入）
        base_parts = _build_base_identity_parts(src.type, content)
        if base_parts:
            parts.append(f"base identity: {_join_parts(base_parts)}")
    else:
        desc = str(content.get("description", "")).strip()
        desc_en = _extract_keywords_from_text(desc)
        if desc_en:
            parts.append(desc_en)

    # Visual style
    vs = str(content.get("visual_style", "")).strip()
    vs_en = _extract_english(vs)
    if vs_en:
        parts.append(f"visual style: {vs_en}")

    # Color palette
    cp = str(content.get("color_palette", "")).strip()
    cp_en = _translate_color_text(cp) if _has_cjk(cp) else cp
    if cp_en:
        parts.append(f"color palette: {cp_en}")

    # Traits: EN labels + EN values
    traits = extract_traits(src.type, content)
    trait_parts: list[str] = []
    for key, value in traits.items():
        val = str(value).strip()
        if not val or val == "未指定":
            continue
        en_val = _translate_trait_value(key, val)
        if en_val:
            label = trait_label(key, "en")
            trait_parts.append(f"{label}: {en_val}")
    if trait_parts:
        parts.append("; ".join(trait_parts))

    # Variant-specific fields (EN extraction only)
    if is_variant and variant and variant.kind != "base":
        vp = str(variant.variant_prompt).strip()
        vp_en = _extract_keywords_from_text(vp, max_len=100)
        if vp_en:
            parts.append(vp_en)

        meaning = str(variant.meaning).strip()
        meaning_en = _extract_keywords_from_text(meaning, max_len=60)
        if meaning_en:
            parts.append(f"context: {meaning_en}")

        label = str(variant.label).strip()
        label_en = _extract_english(label)
        if label_en:
            parts.append(f"variant: {label_en}")

        # 变体类型约束（纯英文）
        if variant.kind == "expression":
            parts.append("only change facial expression")
        elif variant.kind == "pose":
            parts.append("only change body pose and gesture")
        elif variant.kind == "action":
            parts.append("show specific action while keeping character appearance")
    else:
        # Prompt hint
        hint = str(content.get("prompt_hint", "")).strip()
        hint_en = _extract_keywords_from_text(hint)
        if hint_en:
            parts.append(hint_en)

    # Tags
    tags = content.get("tags") or []
    if isinstance(tags, list):
        tag_str = ", ".join(str(t).strip() for t in tags if str(t).strip())
        if tag_str:
            parts.append(f"tags: {tag_str}")

    # Quality
    parts.append("masterpiece, best quality, highly detailed")

    prompt = _join_parts(parts)
    if not prompt:
        prompt, _ = compose_base_image_prompt(src.type, content, language="en")

    return prompt
