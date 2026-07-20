"""EditTimeline subtitle 轨 → ASS 烧录。"""

from __future__ import annotations

import os
import re
from pathlib import Path

from core.edit.export_settings import ExportSettings
from core.edit.subtitle_style import recommend_subtitle_style
from core.models.entities import EditClip

_ASS_SPECIAL = re.compile(r"([\\{}])")


def _ms_to_ass_time(ms: int) -> str:
    ms = max(0, int(ms))
    centis = (ms % 1000) // 10
    total_sec = ms // 1000
    seconds = total_sec % 60
    minutes = (total_sec // 60) % 60
    hours = total_sec // 3600
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centis:02d}"


def _escape_ass_text(text: str) -> str:
    raw = (text or "").strip().replace("\r\n", "\n").replace("\r", "\n")
    parts = raw.split("\n")
    escaped_parts = [_ASS_SPECIAL.sub(r"\\\1", part) for part in parts]
    return r"\N".join(escaped_parts)


def resolve_subtitle_font() -> tuple[str, Path | None]:
    """返回 (ASS Fontname, fontsdir)。"""
    env = os.getenv("SVG_SUBTITLE_FONT", "").strip()
    if env:
        path = Path(env)
        if path.is_file():
            return _font_name_for_file(path), path.parent

    candidates: list[tuple[str, Path]] = [
        ("Microsoft YaHei", Path("C:/Windows/Fonts/msyh.ttc")),
        ("Microsoft YaHei", Path("C:/Windows/Fonts/msyhbd.ttc")),
        ("SimHei", Path("C:/Windows/Fonts/simhei.ttf")),
        ("PingFang SC", Path("/System/Library/Fonts/PingFang.ttc")),
        ("Noto Sans CJK SC", Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")),
        ("Noto Sans CJK SC", Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc")),
        ("DejaVu Sans", Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")),
    ]
    for name, path in candidates:
        if path.is_file():
            return name, path.parent
    return "Arial", None


def _font_name_for_file(path: Path) -> str:
    stem = path.stem.lower()
    if "msyh" in stem or "yahei" in stem:
        return "Microsoft YaHei"
    if "simhei" in stem or "hei" in stem:
        return "SimHei"
    if "noto" in stem:
        return "Noto Sans CJK SC"
    if "pingfang" in stem:
        return "PingFang SC"
    return path.stem


def build_ass_from_subtitle_clips(
    clips: list[EditClip],
    *,
    width: int = 1920,
    height: int = 1080,
    font_name: str | None = None,
) -> str:
    """将 subtitle clip 列表转为 ASS V4+ 文本（底部居中白字黑边）。"""
    if font_name is None:
        font_name, _ = resolve_subtitle_font()

    play_res_x = max(int(width), 1)
    play_res_y = max(int(height), 1)
    style = recommend_subtitle_style(play_res_x, play_res_y)
    ass_style = style["ass"]
    font_size = int(ass_style["font_size_px"])
    margin_v = int(ass_style["margin_v_px"])
    outline_px = int(ass_style.get("outline_px") or 2)

    header = (
        "\ufeff[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {play_res_x}\n"
        f"PlayResY: {play_res_y}\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        f"0,0,0,0,100,100,0,0,1,{outline_px},1,2,40,40,{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    lines: list[str] = [header]
    for clip in sorted(clips, key=lambda c: (c.start_ms, c.end_ms)):
        text = _escape_ass_text(clip.label)
        if not text:
            continue
        start = _ms_to_ass_time(clip.start_ms)
        end = _ms_to_ass_time(max(clip.end_ms, clip.start_ms + 100))
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")
    return "".join(lines)


def write_ass_file(
    clips: list[EditClip],
    path: Path,
    settings: ExportSettings,
) -> bool:
    """写入 ASS 文件；无有效字幕时返回 False。"""
    content = build_ass_from_subtitle_clips(
        clips,
        width=settings.width,
        height=settings.height,
    )
    if content.count("Dialogue:") == 0:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")
    return True


def _ffmpeg_path_arg(path: Path) -> str:
    """FFmpeg ass/subtitles 滤镜路径参数（Windows 盘符冒号转义，无 shell 引号）。

    subprocess 列表传参时不应加单引号；引号会导致 FFmpeg 将路径误解析为 original_size 等选项。
    """
    resolved = path.resolve().as_posix()
    return resolved.replace("\\", "/").replace(":", r"\:")


def build_ass_vf_filter(*, ass_path: Path, fonts_dir: Path | None = None) -> str:
    """构建 ass 滤镜链字符串。"""
    ass_arg = _ffmpeg_path_arg(ass_path)
    if fonts_dir and fonts_dir.is_dir():
        fonts_arg = _ffmpeg_path_arg(fonts_dir)
        return f"ass={ass_arg}:fontsdir={fonts_arg}"
    return f"ass={ass_arg}"


def _escape_drawtext_text(text: str) -> str:
    """drawtext 滤镜 text 参数转义。"""
    raw = (text or "").strip().replace("\r\n", "\n").replace("\r", "\n")
    parts = raw.split("\n")
    escaped = []
    for part in parts:
        part = part.replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'")
        escaped.append(part)
    return r"\n".join(escaped)


def build_drawtext_vf_filters(
    clips: list[EditClip],
    *,
    width: int,
    height: int,
    font_name: str | None = None,
) -> list[str]:
    """将 subtitle clip 转为 drawtext 滤镜链（ASS 失败时的回退方案）。"""
    if font_name is None:
        font_name, _ = resolve_subtitle_font()
    style = recommend_subtitle_style(max(int(width), 1), max(int(height), 1))
    ass_style = style["ass"]
    font_size = int(ass_style["font_size_px"])
    margin_v = int(ass_style["margin_v_px"])
    outline_px = int(ass_style.get("outline_px") or 2)
    y_expr = f"h-th-{margin_v}"
    filters: list[str] = []
    for clip in sorted(clips, key=lambda c: (c.start_ms, c.end_ms)):
        text = _escape_drawtext_text(clip.label)
        if not text:
            continue
        start_sec = max(0, clip.start_ms) / 1000.0
        end_sec = max(clip.end_ms, clip.start_ms + 100) / 1000.0
        filters.append(
            "drawtext="
            f"font='{font_name}':"
            f"text='{text}':"
            f"fontsize={font_size}:"
            f"fontcolor=white:"
            f"borderw={outline_px}:bordercolor=black:"
            f"x=(w-text_w)/2:y={y_expr}:"
            f"enable='between(t,{start_sec:.3f},{end_sec:.3f})'"
        )
    return filters


def burn_subtitles(
    ffmpeg: str,
    video_in: Path,
    ass_path: Path,
    video_out: Path,
    settings: ExportSettings,
    *,
    run_ffmpeg,
    subtitle_clips: list[EditClip] | None = None,
) -> None:
    """将 ASS 硬字幕烧录进视频轨（重编码）；失败时可回退 drawtext。"""
    font_name, fonts_dir = resolve_subtitle_font()
    vf = build_ass_vf_filter(ass_path=ass_path, fonts_dir=fonts_dir)

    def _run_with_vf(filter_chain: str, *, label: str) -> None:
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(video_in),
            "-vf",
            filter_chain,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(settings.fps),
            "-crf",
            str(settings.crf),
            "-an",
            str(video_out),
        ]
        run_ffmpeg(cmd, label=label)

    try:
        _run_with_vf(vf, label="字幕烧录")
    except Exception as ass_exc:
        clips = subtitle_clips or []
        draw_filters = build_drawtext_vf_filters(
            clips,
            width=settings.width,
            height=settings.height,
            font_name=font_name,
        )
        if not draw_filters:
            raise ass_exc
        draw_vf = ",".join(draw_filters)
        _run_with_vf(draw_vf, label="字幕烧录(drawtext回退)")
