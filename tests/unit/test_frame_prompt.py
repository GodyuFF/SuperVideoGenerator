"""画面（frame）prompt 组装测试。"""

from core.assets.image_prompt import compose_frame_image_prompt, compose_image_prompt
from core.models.entities import TextAssetType


def test_compose_frame_prompt_preserves_scene_reference():
    content = {
        "image_prompt": "主角站在窗边望向城市",
        "summary": "窗边眺望",
    }
    prompt, negative = compose_frame_image_prompt(content)
    assert "preserve scene layout" in prompt
    assert "主角站在窗边" in prompt
    assert "green screen" in negative


def test_compose_frame_prompt_reads_legacy_description():
    """旧存盘仅有 description 时仍能组装。"""
    content = {
        "description": "主角站在窗边望向城市",
        "composition_prompt": "medium shot, warm lighting",
    }
    prompt, _ = compose_frame_image_prompt(content)
    assert "主角站在窗边" in prompt
    assert "medium shot" in prompt


def test_compose_scene_stronger_no_people_negative():
    content = {"description": "清晨城市天际线，薄雾笼罩的高楼与河流。" * 4}
    prompt, negative = compose_image_prompt(TextAssetType.SCENE, content)
    assert "environment background plate" in prompt
    assert "chroma key residue" in negative
    assert "generated characters" in negative
    assert "narrative scene" in negative
