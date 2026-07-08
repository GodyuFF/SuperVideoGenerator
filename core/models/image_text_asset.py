"""图文资产领域模型：character / prop / scene 统一 content 结构与规范化。"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.models.entities import MediaAsset, TextAsset, TextAssetType, new_id


class ImageTextAssetType(str, Enum):
    """图文资产类型（角色、物品、场景、画面）。"""

    CHARACTER = "character"
    PROP = "prop"
    SCENE = "scene"
    FRAME = "frame"


IMAGE_TEXT_ASSET_TYPES = frozenset(t.value for t in ImageTextAssetType)

_VALID_VARIANT_KINDS = frozenset(
    {"base", "expression", "pose", "action", "costume", "other"}
)
ImageVariantKind = Literal[
    "base", "expression", "pose", "action", "costume", "other"
]
ImageVariantStatus = Literal["pending", "ready", "failed"]

MAX_IMAGE_VARIANTS_PER_ASSET = 8


class ImageVariant(BaseModel):
    """单张变体图：设定主形象或表情/姿态/动作衍生图。"""

    id: str = Field(default_factory=lambda: new_id("var"))
    kind: ImageVariantKind = "expression"
    label: str = ""
    meaning: str = ""
    variant_prompt: str = ""
    image_prompt: str = ""
    media_id: str | None = None
    reference_variant_id: str = ""
    status: ImageVariantStatus = "pending"
    prompt_locked: bool = False


class ImageTextAssetContentBase(BaseModel):
    """三类图文资产共用 content 字段。"""

    summary: str = ""
    description: str = ""
    visual_style: str = ""
    color_palette: str = ""
    tags: list[str] = Field(default_factory=list)
    prompt_hint: str = ""
    display_mode: Literal["static_image", "dynamic_image"] = "static_image"
    notes: str = ""
    image_prompt: str = ""
    negative_prompt: str = ""
    prompt_version: int = 0
    prompt_locked: bool = False
    image_variants: list[dict[str, Any]] = Field(default_factory=list)


class CharacterTraits(BaseModel):
    role: str = ""
    personality: str = ""
    age_range: str = ""
    gender: str = ""
    costume: str = ""
    distinctive_features: str = ""
    ethnicity: str = ""
    body_type: str = ""
    height: str = ""
    build: str = ""
    hair_style: str = ""
    hair_color: str = ""
    eye_color: str = ""
    facial_features: str = ""
    default_expression: str = ""
    default_pose: str = ""
    accessories: str = ""


class SceneTraits(BaseModel):
    location: str = ""
    time_of_day: str = ""
    weather: str = ""
    lighting: str = ""
    mood: str = ""
    spatial_layout: str = ""
    architecture_style: str = ""
    key_objects: str = ""
    foreground: str = ""
    background: str = ""
    camera_angle: str = ""
    depth_of_field: str = ""
    color_tone: str = ""


class PropTraits(BaseModel):
    category: str = ""
    material: str = ""
    size_scale: str = ""
    usage: str = ""
    condition: str = ""
    shape: str = ""
    color: str = ""
    texture: str = ""
    brand_style: str = ""
    visual_details: str = ""


class CharacterContent(ImageTextAssetContentBase):
    role: str = ""
    personality: str = ""
    age_range: str = ""
    gender: str = ""
    costume: str = ""
    distinctive_features: str = ""
    ethnicity: str = ""
    body_type: str = ""
    height: str = ""
    build: str = ""
    hair_style: str = ""
    hair_color: str = ""
    eye_color: str = ""
    facial_features: str = ""
    default_expression: str = ""
    default_pose: str = ""
    accessories: str = ""


class SceneContent(ImageTextAssetContentBase):
    location: str = ""
    time_of_day: str = ""
    weather: str = ""
    lighting: str = ""
    mood: str = ""
    spatial_layout: str = ""
    architecture_style: str = ""
    key_objects: str = ""
    foreground: str = ""
    background: str = ""
    camera_angle: str = ""
    depth_of_field: str = ""
    color_tone: str = ""


class PropContent(ImageTextAssetContentBase):
    category: str = ""
    material: str = ""
    size_scale: str = ""
    usage: str = ""
    condition: str = ""
    shape: str = ""
    color: str = ""
    texture: str = ""
    brand_style: str = ""
    visual_details: str = ""


class FrameContent(ImageTextAssetContentBase):
    """分镜画面：多参考图合成，element_refs 指向空镜/角色/物品。"""

    element_refs: dict[str, list[str]] = Field(default_factory=dict)
    variant_refs: dict[str, str] = Field(default_factory=dict)
    shot_id: str = ""
    composition_prompt: str = ""
    reference_order: list[str] = Field(
        default_factory=lambda: ["scene", "character", "prop"]
    )


_CONTENT_MODEL: dict[str, type[BaseModel]] = {
    ImageTextAssetType.CHARACTER.value: CharacterContent,
    ImageTextAssetType.SCENE.value: SceneContent,
    ImageTextAssetType.PROP.value: PropContent,
    ImageTextAssetType.FRAME.value: FrameContent,
}

_TRAIT_KEYS: dict[str, frozenset[str]] = {
    ImageTextAssetType.CHARACTER.value: frozenset(CharacterTraits.model_fields),
    ImageTextAssetType.SCENE.value: frozenset(SceneTraits.model_fields),
    ImageTextAssetType.PROP.value: frozenset(PropTraits.model_fields),
}

_TRAIT_LABELS_ZH: dict[str, str] = {
    "role": "角色定位",
    "personality": "性格",
    "age_range": "年龄",
    "gender": "性别",
    "costume": "服装",
    "distinctive_features": "标志特征",
    "ethnicity": "族裔/人种",
    "body_type": "体型",
    "height": "身高",
    "build": "体格",
    "hair_style": "发型",
    "hair_color": "发色",
    "eye_color": "瞳色",
    "facial_features": "面部特征",
    "default_expression": "默认表情",
    "default_pose": "默认姿态",
    "accessories": "配饰",
    "location": "地点",
    "time_of_day": "时段",
    "weather": "天气",
    "lighting": "光线",
    "mood": "氛围",
    "spatial_layout": "空间布局",
    "architecture_style": "建筑风格",
    "key_objects": "关键物体",
    "foreground": "前景",
    "background": "背景",
    "camera_angle": "机位角度",
    "depth_of_field": "景深",
    "color_tone": "色调",
    "category": "类别",
    "material": "材质",
    "size_scale": "尺寸",
    "usage": "用途",
    "condition": "状态",
    "shape": "形状",
    "color": "颜色",
    "texture": "纹理",
    "brand_style": "品牌风格",
    "visual_details": "视觉细节",
}

_TRAIT_LABELS_EN: dict[str, str] = {
    "role": "role",
    "personality": "personality",
    "age_range": "age",
    "gender": "gender",
    "costume": "costume",
    "distinctive_features": "distinctive features",
    "ethnicity": "ethnicity",
    "body_type": "body type",
    "height": "height",
    "build": "build",
    "hair_style": "hair style",
    "hair_color": "hair color",
    "eye_color": "eye color",
    "facial_features": "facial features",
    "default_expression": "default expression",
    "default_pose": "default pose",
    "accessories": "accessories",
    "location": "location",
    "time_of_day": "time of day",
    "weather": "weather",
    "lighting": "lighting",
    "mood": "mood",
    "spatial_layout": "spatial layout",
    "architecture_style": "architecture style",
    "key_objects": "key objects",
    "foreground": "foreground",
    "background": "background",
    "camera_angle": "camera angle",
    "depth_of_field": "depth of field",
    "color_tone": "color tone",
    "category": "category",
    "material": "material",
    "size_scale": "size scale",
    "usage": "usage",
    "condition": "condition",
    "shape": "shape",
    "color": "color",
    "texture": "texture",
    "brand_style": "brand style",
    "visual_details": "visual details",
}


def is_image_text_asset(asset_type: Any) -> bool:
    val = asset_type.value if hasattr(asset_type, "value") else str(asset_type)
    return val in IMAGE_TEXT_ASSET_TYPES


def trait_keys_for_type(asset_type: Any) -> frozenset[str]:
    type_val = asset_type.value if hasattr(asset_type, "value") else str(asset_type)
    return _TRAIT_KEYS.get(type_val, frozenset())


def trait_label_zh(key: str) -> str:
    return _TRAIT_LABELS_ZH.get(key, key)


def trait_label_en(key: str) -> str:
    """返回英文 trait 标签（用于 Stable Diffusion 等英文生图模型）。"""
    return _TRAIT_LABELS_EN.get(key, key)


def trait_label(key: str, language: str = "zh") -> str:
    """根据语言返回 trait 标签。language: 'zh' | 'en'。"""
    if language == "en":
        return trait_label_en(key)
    return trait_label_zh(key)


def _legacy_description(raw: dict[str, Any]) -> str:
    for key in ("description", "appearance", "text", "body"):
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def parse_image_variants(content: dict[str, Any]) -> list[ImageVariant]:
    """从 content 解析 image_variants 列表。"""
    raw_list = content.get("image_variants")
    if not isinstance(raw_list, list):
        return []
    variants: list[ImageVariant] = []
    for raw in raw_list:
        if not isinstance(raw, dict):
            continue
        try:
            variants.append(ImageVariant.model_validate(raw))
        except Exception:
            continue
    return variants


def variants_to_dicts(variants: list[ImageVariant]) -> list[dict[str, Any]]:
    return [v.model_dump() for v in variants]


def get_base_variant(content: dict[str, Any]) -> ImageVariant | None:
    for v in parse_image_variants(content):
        if v.kind == "base":
            return v
    return None


def find_variant(content: dict[str, Any], variant_id: str) -> ImageVariant | None:
    vid = str(variant_id).strip()
    if not vid:
        return None
    for v in parse_image_variants(content):
        if v.id == vid:
            return v
    return None


def resolve_variant_media_id(content: dict[str, Any], variant_id: str) -> str | None:
    v = find_variant(content, variant_id)
    if v and v.media_id:
        return v.media_id
    return None


def ensure_image_variants(
    content: dict[str, Any],
    *,
    primary_media_id: str | None = None,
) -> dict[str, Any]:
    """保证存在 base 变体；同步 primary_media_id 到 base。"""
    out = dict(content)
    variants = parse_image_variants(out)
    base = get_base_variant(out)
    if base is None:
        base = ImageVariant(
            kind="base",
            label="主形象",
            meaning="角色/场景/道具设定主视觉",
            status="pending",
        )
        if str(out.get("image_prompt", "")).strip():
            base = base.model_copy(
                update={"image_prompt": str(out.get("image_prompt", "")).strip()}
            )
        variants.insert(0, base)
    else:
        idx = next(i for i, v in enumerate(variants) if v.kind == "base")
        variants[idx] = base

    pm = (primary_media_id or "").strip()
    if pm:
        for i, v in enumerate(variants):
            if v.kind == "base":
                variants[i] = v.model_copy(update={"media_id": pm, "status": "ready"})
                break

    for i, v in enumerate(variants):
        if v.kind != "base" and not v.reference_variant_id:
            variants[i] = v.model_copy(update={"reference_variant_id": base.id})

    if len(variants) > MAX_IMAGE_VARIANTS_PER_ASSET:
        variants = variants[:MAX_IMAGE_VARIANTS_PER_ASSET]

    out["image_variants"] = variants_to_dicts(variants)
    return out


def update_variant_in_content(
    content: dict[str, Any],
    variant_id: str,
    **updates: Any,
) -> dict[str, Any]:
    """更新指定变体字段并写回 content。"""
    out = dict(content)
    variants = parse_image_variants(out)
    found = False
    new_list: list[ImageVariant] = []
    for v in variants:
        if v.id == variant_id:
            new_list.append(v.model_copy(update=updates))
            found = True
        else:
            new_list.append(v)
    if not found:
        return out
    out["image_variants"] = variants_to_dicts(new_list)
    return out


def merge_incoming_variants(
    content: dict[str, Any],
    incoming: list[Any],
) -> dict[str, Any]:
    """合并 LLM 提交的变体（保留已有 media_id）。"""
    if not incoming:
        return content
    out = ensure_image_variants(content)
    existing = {v.id: v for v in parse_image_variants(out)}
    base = get_base_variant(out)
    base_id = base.id if base else ""
    merged: list[ImageVariant] = []
    seen_base = False
    for raw in incoming:
        if not isinstance(raw, dict):
            continue
        kind_raw = str(raw.get("kind", "other")).strip()
        kind: ImageVariantKind = (
            kind_raw if kind_raw in _VALID_VARIANT_KINDS else "other"
        )
        if kind == "base":
            seen_base = True
        label = str(raw.get("label", "")).strip()
        if not label and kind != "base":
            continue
        vid = str(raw.get("id", "")).strip() or new_id("var")
        prev = existing.get(vid)
        ref_vid = str(raw.get("reference_variant_id", "")).strip()
        if kind != "base" and not ref_vid:
            ref_vid = base_id
        merged.append(
            ImageVariant(
                id=vid,
                kind=kind,
                label=label or ("主形象" if kind == "base" else label),
                meaning=str(raw.get("meaning", prev.meaning if prev else "")).strip(),
                variant_prompt=str(
                    raw.get("variant_prompt", prev.variant_prompt if prev else "")
                ).strip(),
                image_prompt=str(
                    raw.get("image_prompt", prev.image_prompt if prev else "")
                ).strip(),
                media_id=prev.media_id if prev else raw.get("media_id"),
                reference_variant_id=ref_vid,
                status=prev.status if prev and prev.media_id else "pending",
                prompt_locked=bool(raw.get("prompt_locked", prev.prompt_locked if prev else False)),
            )
        )
    if not seen_base and base:
        merged.insert(0, base)
    if len(merged) > MAX_IMAGE_VARIANTS_PER_ASSET:
        merged = merged[:MAX_IMAGE_VARIANTS_PER_ASSET]
    out["image_variants"] = variants_to_dicts(merged)
    return out


def normalize_image_text_content(asset_type: Any, raw: Any) -> dict[str, Any]:
    """将 LLM/旧数据 content 规范为图文资产结构化 dict。"""
    type_val = asset_type.value if hasattr(asset_type, "value") else str(asset_type)
    model_cls = _CONTENT_MODEL.get(type_val, ImageTextAssetContentBase)

    if isinstance(raw, str) and raw.strip():
        raw = {"description": raw.strip()}
    elif not isinstance(raw, dict):
        raw = {}

    merged = dict(raw)
    if not merged.get("description"):
        legacy = _legacy_description(merged)
        if legacy:
            merged["description"] = legacy

    if "tags" in merged and not isinstance(merged["tags"], list):
        tags = merged["tags"]
        if isinstance(tags, str):
            merged["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
        else:
            merged["tags"] = []

    dm = str(merged.get("display_mode", "static_image")).strip()
    if dm not in ("static_image", "dynamic_image"):
        merged["display_mode"] = "static_image"
    else:
        merged["display_mode"] = dm

    for key in ("image_prompt", "negative_prompt"):
        val = merged.get(key)
        if isinstance(val, (list, tuple)):
            merged[key] = ", ".join(str(x).strip() for x in val if str(x).strip())
        elif val is not None and not isinstance(val, str):
            merged[key] = str(val)

    parsed = model_cls.model_validate(merged)
    result = parsed.model_dump()
    if type_val == ImageTextAssetType.FRAME.value:
        if not isinstance(result.get("element_refs"), dict):
            result["element_refs"] = {}
        if not result.get("reference_order"):
            result["reference_order"] = ["scene", "character", "prop"]
        return result
    if isinstance(raw.get("image_variants"), list):
        result = merge_incoming_variants(result, raw["image_variants"])
    return ensure_image_variants(result)


def extract_traits(asset_type: Any, content: dict[str, Any]) -> dict[str, str]:
    """提取类型扩展字段子集，供看板展示。"""
    type_val = asset_type.value if hasattr(asset_type, "value") else str(asset_type)
    keys = _TRAIT_KEYS.get(type_val, frozenset())
    return {k: str(content.get(k, "")) for k in keys if content.get(k)}


def image_text_preview(content: dict[str, Any], *, max_len: int = 80) -> str:
    """卡片预览文案：summary 优先，否则 description 截断。"""
    summary = str(content.get("summary", "")).strip()
    if summary:
        return summary[:max_len] + ("…" if len(summary) > max_len else "")
    prompt = str(content.get("image_prompt", "")).strip()
    if prompt:
        return prompt[:max_len] + ("…" if len(prompt) > max_len else "")
    desc = str(content.get("description", "")).strip()
    if not desc:
        return ""
    return desc[:max_len] + ("…" if len(desc) > max_len else "")


class ImageTextAsset(BaseModel):
    """图文资产视图：TextAsset + 关联媒体。"""

    id: str
    project_id: str
    type: ImageTextAssetType
    name: str
    content: dict[str, Any] = Field(default_factory=dict)
    traits: dict[str, str] = Field(default_factory=dict)
    scope: str
    status: str
    user_edited: bool = False
    source_script_id: str | None = None
    primary_media_id: str | None = None
    reuse_policy: str = "shared"
    images: list[dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def from_text_asset(
        cls,
        asset: TextAsset,
        *,
        images: list[MediaAsset] | None = None,
    ) -> "ImageTextAsset":
        type_val = asset.type.value
        content = normalize_image_text_content(asset.type, asset.content)
        media_items = images or []
        image_dicts = [
            {
                "id": m.id,
                "url": m.url,
                "name": m.name,
                "type": m.type.value,
            }
            for m in media_items
        ]
        return cls(
            id=asset.id,
            project_id=asset.project_id,
            type=ImageTextAssetType(type_val),
            name=asset.name,
            content=content,
            traits=extract_traits(asset.type, content),
            scope=asset.scope.value,
            status=asset.status.value,
            user_edited=asset.user_edited,
            source_script_id=asset.source_script_id,
            primary_media_id=asset.primary_media_id,
            reuse_policy=asset.reuse_policy,
            images=image_dicts,
        )


def image_text_asset_from_text_asset(
    asset: TextAsset,
    *,
    images: list[MediaAsset] | None = None,
) -> ImageTextAsset:
    return ImageTextAsset.from_text_asset(asset, images=images)


def upgrade_text_asset_content(asset: TextAsset) -> TextAsset:
    """惰性升级图文资产 content 结构。"""
    if not is_image_text_asset(asset.type):
        return asset
    normalized = normalize_image_text_content(asset.type, asset.content)
    normalized = ensure_image_variants(
        normalized, primary_media_id=asset.primary_media_id
    )
    if not str(normalized.get("image_prompt", "")).strip():
        from core.assets.image_prompt import apply_composed_prompts

        normalized = apply_composed_prompts(
            asset.type, normalized, preserve_prompt_lock=True
        )
    if normalized == asset.content:
        return asset
    return asset.model_copy(update={"content": normalized})
