"""EditTimeline subtitle 轨 → ASS 烧录。"""

from __future__ import annotations

import os
import re
from pathlib import Path

from core.edit.export_settings import ExportSettings
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
    font_size = max(32, min(72, play_res_y // 18))
    margin_v = max(40, play_res_y // 12)

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
        f"0,0,0,0,100,100,0,0,1,2,1,2,40,40,{margin_v},1\n"
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
    """FFmpeg 滤镜参数用路径（Windows 反斜杠转义）。"""
    resolved = path.resolve().as_posix()
    return resolved.replace(":", r"\:")


def burn_subtitles(
    ffmpeg: str,
    video_in: Path,
    ass_path: Path,
    video_out: Path,
    settings: ExportSettings,
    *,
    run_ffmpeg,
) -> None:
    """将 ASS 硬字幕烧录进视频轨（重编码）。"""
    _, fonts_dir = resolve_subtitle_font()
    ass_arg = _ffmpeg_path_arg(ass_path)
    if fonts_dir and fonts_dir.is_dir():
        fonts_arg = _ffmpeg_path_arg(fonts_dir)
        vf = f"ass={ass_arg}:fontsdir={fonts_arg}"
    else:
        vf = f"ass={ass_arg}"

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_in),
        "-vf",
        vf,
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
    run_ffmpeg(cmd, label="字幕烧录")
