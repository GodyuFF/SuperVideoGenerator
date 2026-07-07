"""ImageVariant 模型与 prompt 组装测试。"""

from core.assets.image_prompt import compose_base_image_prompt, compose_variant_image_prompt
from core.models.entities import TextAssetType
from core.models.image_text_asset import (
    ImageVariant,
    ensure_image_variants,
    get_base_variant,
    merge_incoming_variants,
    normalize_image_text_content,
    parse_image_variants,
    resolve_variant_media_id,
)
from tests.support.image_text_fixtures import character_content


def test_normalize_creates_implicit_base_variant():
    raw = character_content(summary="测试角色")
    content = normalize_image_text_content(TextAssetType.CHARACTER, raw)
    variants = parse_image_variants(content)
    assert len(variants) >= 1
    base = get_base_variant(content)
    assert base is not None
    assert base.kind == "base"
    assert base.label == "主形象"


def test_merge_incoming_variants_preserves_media():
    content = normalize_image_text_content(
        TextAssetType.CHARACTER, character_content(summary="虎")
    )
    content = ensure_image_variants(content, primary_media_id="media_base")
    merged = merge_incoming_variants(
        content,
        [
            {
                "kind": "expression",
                "label": "严肃",
                "meaning": "对峙场景",
                "variant_prompt": "严肃表情，眉头微皱",
            }
        ],
    )
    variants = parse_image_variants(merged)
    assert len(variants) == 2
    expr = [v for v in variants if v.kind == "expression"][0]
    assert expr.label == "严肃"
    base = get_base_variant(merged)
    assert base and base.media_id == "media_base"
    assert expr.reference_variant_id == base.id


def test_resolve_variant_media_id():
    content = normalize_image_text_content(TextAssetType.CHARACTER, {})
    content = merge_incoming_variants(
        content,
        [{"kind": "expression", "label": "笑", "variant_prompt": "微笑"}],
    )
    v = [x for x in parse_image_variants(content) if x.kind == "expression"][0]
    content = ensure_image_variants(content)
    content = normalize_image_text_content(
        TextAssetType.CHARACTER,
        {**content, "image_variants": [{**v.model_dump(), "media_id": "media_x"}]},
    )
    assert resolve_variant_media_id(content, v.id) == "media_x"


def test_compose_variant_prompt_includes_consistency():
    content = normalize_image_text_content(
        TextAssetType.CHARACTER, character_content(summary="角色A")
    )
    variant = ImageVariant(
        kind="expression",
        label="惊讶",
        variant_prompt="瞪大眼睛",
        meaning="发现秘密",
    )
    prompt, _ = compose_variant_image_prompt(TextAssetType.CHARACTER, content, variant)
    assert "same character" in prompt.lower()
    assert "惊讶" in prompt or "瞪大眼睛" in prompt
