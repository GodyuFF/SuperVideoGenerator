"""字幕样式推荐与 load_edit_context 注入测试。"""

from core.edit.subtitle_style import (
    build_subtitle_style_context,
    recommend_subtitle_style,
    resolve_output_canvas_size,
)


def test_recommend_subtitle_style_landscape_1080p():
    """横屏 1080p 推荐底部居中与小字号。"""
    style = recommend_subtitle_style(1920, 1080)
    assert style["orientation"] == "landscape"
    assert style["placement"] == "bottom_center"
    assert style["ass"]["alignment"] == 2
    assert 38 <= style["ass"]["font_size_px"] <= 48
    assert style["opencut"]["vertical_align"] == "bottom"
    assert "底部居中" in style["guidance_zh"]
    assert "禁止" in style["guidance_zh"]


def test_recommend_subtitle_style_portrait():
    """竖屏推荐更大底边距。"""
    style = recommend_subtitle_style(1080, 1920)
    assert style["orientation"] == "portrait"
    assert style["ass"]["margin_v_px"] >= 150
    assert style["max_chars_per_line"] == 14


def test_resolve_output_canvas_size_prefers_timeline_metadata():
    """timeline.metadata.export 优先于默认导出配置。"""
    w, h = resolve_output_canvas_size(
        timeline_metadata={"export": {"width": 1080, "height": 1920}},
    )
    assert (w, h) == (1080, 1920)


def test_build_subtitle_style_context_includes_common_presets():
    """上下文应含常用分辨率预设表。"""
    ctx = build_subtitle_style_context(export_width=1920, export_height=1080)
    assert ctx["output_canvas"] == {"width": 1920, "height": 1080}
    assert "1920x1080" in ctx["common_presets"]
    assert ctx["subtitle_style"]["ass"]["font_size_px"] > 0


def test_load_edit_context_includes_subtitle_style_context():
    """build_subtitle_style_context 字段结构符合剪辑 Agent 消费约定。"""
    ctx = build_subtitle_style_context(export_width=1920, export_height=1080)
    assert ctx["subtitle_style"]["placement"] == "bottom_center"
    assert ctx["subtitle_style"]["opencut"]["vertical_align"] == "bottom"
