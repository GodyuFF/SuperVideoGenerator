"""生图 prompt 组装器测试。"""

from core.assets.image_prompt import (
    PROMPT_VERSION,
    compose_image_prompt,
    compose_variant_image_prompt,
    finalize_image_text_content,
)
from core.models.entities import StyleConfig, TextAssetType, VideoStyleMode
from core.models.image_text_asset import ImageVariant


def test_compose_character_prompt_includes_traits_and_style():
    content = {
        "description": "年轻女性，短发，都市休闲装",
        "role": "主角",
        "hair_color": "黑色",
        "visual_style": "写实插画",
        "color_palette": "暖色",
        "prompt_hint": "电影感侧光",
    }
    style = StyleConfig(
        mode=VideoStyleMode.STORYBOOK,
        aspect_ratio="16:9",
    )
    prompt, negative = compose_image_prompt(
        TextAssetType.CHARACTER, content, project_style=style
    )
    assert "年轻女性" in prompt
    assert "发色: 黑色" in prompt
    assert "写实插画" in prompt
    assert "aspect ratio 16:9" in prompt
    assert "chroma key green" in prompt.lower()
    assert negative
    assert "watermark" in negative
    assert "complex background" in negative


def test_compose_scene_empty_shot_no_people():
    content = {
        "description": "清晨城市天际线，薄雾笼罩的高楼与河流。" * 4,
        "key_objects": "路灯、长椅",
        "foreground": "湿润路面",
        "background": "高楼天际线",
    }
    prompt, negative = compose_image_prompt(TextAssetType.SCENE, content)
    assert "environment background plate" in prompt
    assert "matte backdrop" in prompt
    assert "background layer only" in prompt
    assert "environment fixed fixtures only" in prompt
    assert "scenery only, no figures" in prompt
    assert "people" in negative
    assert "human" in negative
    assert "pedestrian" in negative
    assert "main subject" in negative


def test_compose_prop_chroma_background():
    content = {"description": "古代青铜酒樽，表面有铜绿锈迹。" * 4}
    prompt, negative = compose_image_prompt(TextAssetType.PROP, content)
    assert "chroma key green" in prompt.lower()
    assert "complex background" in negative


def test_compose_variant_scene_no_people():
    content = {"description": "测试场景描述足够长用于生图组装验证。" * 3}
    variant = ImageVariant(kind="other", label="夜景", variant_prompt="night lighting")
    prompt, negative = compose_variant_image_prompt(
        TextAssetType.SCENE, content, variant
    )
    assert "empty background plate" in prompt
    assert "no prop subjects" in prompt
    assert "no people" in prompt


def test_compose_variant_character_chroma():
    content = {"description": "测试角色描述足够长用于生图组装验证。" * 3}
    variant = ImageVariant(kind="pose", label="奔跑", variant_prompt="running pose")
    prompt, _ = compose_variant_image_prompt(TextAssetType.CHARACTER, content, variant)
    assert "chroma key green" in prompt.lower()


def test_finalize_sets_prompt_version():
    content = finalize_image_text_content(
        TextAssetType.SCENE,
        {"description": "测试场景描述足够长用于生图组装验证。" * 3},
    )
    assert content["image_prompt"]
    assert content["negative_prompt"]
    assert content["prompt_version"] == PROMPT_VERSION
    assert content["prompt_version"] == 2
    assert "environment background plate" in content["image_prompt"]


def test_finalize_respects_prompt_locked():
    locked = {
        "description": "原始描述",
        "image_prompt": "用户锁定 prompt",
        "prompt_locked": True,
    }
    content = finalize_image_text_content(TextAssetType.PROP, locked)
    assert content["image_prompt"] == "用户锁定 prompt"
