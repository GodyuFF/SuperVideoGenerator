"""字幕轨导出为 SRT 文件。"""

from __future__ import annotations

from core.models.entities import EditTimeline


def _ms_to_srt_time(ms: int) -> str:
    """将毫秒转为 SRT 时间码 HH:MM:SS,mmm。"""
    total_ms = max(0, int(ms))
    hours = total_ms // 3_600_000
    minutes = (total_ms % 3_600_000) // 60_000
    seconds = (total_ms % 60_000) // 1000
    millis = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def write_srt(timeline: EditTimeline) -> str:
    """将 subtitle 轨转为 SRT 文本；无字幕时返回空字符串。"""
    clips = sorted(
        timeline.tracks.get("subtitle", []),
        key=lambda c: (c.start_ms, c.end_ms),
    )
    if not clips:
        return ""

    blocks: list[str] = []
    for idx, clip in enumerate(clips, start=1):
        text = (clip.label or "").strip()
        if not text:
            continue
        blocks.append(
            "\n".join(
                [
                    str(idx),
                    f"{_ms_to_srt_time(clip.start_ms)} --> {_ms_to_srt_time(clip.end_ms)}",
                    text,
                    "",
                ]
            )
        )
    return "\n".join(blocks).strip() + ("\n" if blocks else "")
