from core.llm.prompt.tools.schema_builders import build_sub_shot_schema, build_sub_shot_image_schema


def test_sub_shot_schema_has_produce_mode():
    s = build_sub_shot_schema()
    assert "produce_mode" in s["properties"]
    assert set(s["properties"]["produce_mode"]["enum"]) == {"still", "text2video", "img2video"}


def test_sub_shot_image_schema_has_timing():
    s = build_sub_shot_image_schema()
    assert "start_ms" in s["properties"] and "end_ms" in s["properties"]
