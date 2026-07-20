"""按成片画布分辨率推荐字幕字号、边距与对齐方式。"""

from __future__ import annotations

from typing import Any

# 与 OpenCut `FONT_SIZE_SCALE_REFERENCE` 保持一致
OPENCUT_FONT_SIZE_SCALE_REFERENCE = 90


def _orientation(width: int, height: int) -> str:
    """根据宽高比判断横屏/竖屏/方形。"""
    if width > height * 1.1:
        return "landscape"
    if height > width * 1.1:
        return "portrait"
    return "square"


def recommend_subtitle_style(width: int, height: int) -> dict[str, Any]:
    """按输出画布尺寸生成字幕样式建议（ASS 烧录 + OpenCut 文本轨）。"""
    canvas_w = max(int(width), 1)
    canvas_h = max(int(height), 1)
    orient = _orientation(canvas_w, canvas_h)

    if orient == "portrait":
        font_ratio = 0.044
        margin_ratio = 0.10
        max_width_ratio = 0.90
        max_chars_per_line = 14
    elif orient == "square":
        font_ratio = 0.040
        margin_ratio = 0.08
        max_width_ratio = 0.85
        max_chars_per_line = 16
    else:
        font_ratio = 0.039
        margin_ratio = 0.08
        max_width_ratio = 0.85
        max_chars_per_line = 18

    font_size_px = max(28, min(72, round(canvas_h * font_ratio)))
    margin_v_px = max(32, min(200, round(canvas_h * margin_ratio)))
    margin_vertical_ratio = round(margin_v_px / canvas_h, 4)
    font_size_ratio = round(font_size_px / canvas_h, 4)
    opencut_font_size = round(
        font_size_px / canvas_h * OPENCUT_FONT_SIZE_SCALE_REFERENCE,
        2,
    )

    return {
        "canvas_width": canvas_w,
        "canvas_height": canvas_h,
        "orientation": orient,
        "placement": "bottom_center",
        "max_chars_per_line": max_chars_per_line,
        "ass": {
            "alignment": 2,
            "font_size_px": font_size_px,
            "margin_v_px": margin_v_px,
            "outline_px": 2,
        },
        "opencut": {
            "font_size_units": opencut_font_size,
            "font_size_ratio_of_play_height": font_size_ratio,
            "text_align": "center",
            "vertical_align": "bottom",
            "margin_vertical_ratio": margin_vertical_ratio,
            "max_line_width_ratio": max_width_ratio,
            "font_weight": "bold",
            "color": "#ffffff",
        },
        "guidance_zh": (
            f"成片 {canvas_w}×{canvas_h}（{orient}）：字幕须 **底部居中**，"
            f"禁止放在画面正中；字号约 {font_size_px}px（画布高度 {font_size_ratio:.1%}），"
            f"底边距约 {margin_vertical_ratio:.1%}（≈{margin_v_px}px），"
            f"单行建议不超过 {max_chars_per_line} 个汉字，过长须按句拆成多条 subtitle clip。"
        ),
    }


def resolve_output_canvas_size(
    *,
    timeline_metadata: dict[str, Any] | None = None,
    export_width: int | None = None,
    export_height: int | None = None,
) -> tuple[int, int]:
    """解析剪辑/导出使用的画布宽高（timeline.metadata.export 优先）。"""
    if isinstance(timeline_metadata, dict):
        export_meta = timeline_metadata.get("export")
        if isinstance(export_meta, dict):
            w = int(export_meta.get("width") or 0)
            h = int(export_meta.get("height") or 0)
            if w > 0 and h > 0:
                return w, h

    if export_width and export_height and export_width > 0 and export_height > 0:
        return int(export_width), int(export_height)

    from core.edit.export_settings import get_export_manager

    settings = get_export_manager().get_settings()
    return settings.width, settings.height


def build_subtitle_style_context(
    *,
    timeline_metadata: dict[str, Any] | None = None,
    export_width: int | None = None,
    export_height: int | None = None,
) -> dict[str, Any]:
    """供 load_edit_context / capabilities 使用的字幕样式上下文。"""
    width, height = resolve_output_canvas_size(
        timeline_metadata=timeline_metadata,
        export_width=export_width,
        export_height=export_height,
    )
    preset = recommend_subtitle_style(width, height)
    return {
        "output_canvas": {"width": width, "height": height},
        "subtitle_style": preset,
        "common_presets": {
            "1920x1080": recommend_subtitle_style(1920, 1080),
            "1080x1920": recommend_subtitle_style(1080, 1920),
            "1280x720": recommend_subtitle_style(1280, 720),
        },
    }
