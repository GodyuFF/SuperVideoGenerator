"""字幕轨与 TTS audio 对齐（TTS cue → WhisperX → 标点比例 fallback）。"""

from __future__ import annotations

from typing import Any

from core.models.entities import EditTimeline, VideoPlan
from core.store.memory import MemoryStore
from core.tts.subtitle import (
    normalize_non_overlapping_cues,
    populate_legacy_submaker_with_full_text,
    subtitle_cues_from_submaker,
)
from edge_tts import SubMaker


def cues_from_media_metadata(media) -> list[dict[str, Any]]:
    """从 MediaAsset.metadata 读取 subtitle_cues。"""
    raw = (media.metadata or {}).get("subtitle_cues")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict) and item.get("text"):
            out.append(dict(item))
    return out


def _proportional_fallback_cues(text: str, duration_ms: int) -> list[dict[str, Any]]:
    """无引擎时间戳时按标点 + 字数比例切分时长。"""
    if duration_ms <= 0:
        return [
            {
                "start_ms": 0,
                "end_ms": 1000,
                "text": text,
                "character": "",
                "color": "",
                "source": "proportional",
            }
        ]
    duration_sec = max(duration_ms / 1000.0, 0.1)
    sub_maker = populate_legacy_submaker_with_full_text(SubMaker(), text, duration_sec)
    cues = subtitle_cues_from_submaker(sub_maker)
    for cue in cues:
        cue.setdefault("source", "proportional")
        cue.setdefault("character", "")
        cue.setdefault("color", "")
    return cues


def cues_are_proportional_only(cues: list[dict[str, Any]]) -> bool:
    """是否全部为字数比例估时（非引擎/对齐结果）。"""
    if not cues:
        return False
    return all(str(c.get("source") or "") == "proportional" for c in cues)


def build_cues_for_audio_media(
    store: MemoryStore,
    media,
    *,
    narration_text: str = "",
    prefer_audio: bool = False,
) -> list[dict[str, Any]]:
    """生成句级 cue：引擎 cues → WhisperX 对齐/ASR →（有文案时）字数比例。

    prefer_audio=True 时跳过纯比例估时，优先音频接地（TTS 边界或 WhisperX）。
    """
    _ = store
    cues = cues_from_media_metadata(media)
    if cues and not (prefer_audio and cues_are_proportional_only(cues)):
        return normalize_non_overlapping_cues(cues)

    text = narration_text.strip() or str((media.metadata or {}).get("narration_text") or "").strip()

    from core.edit.whisperx_align import build_cues_via_whisperx

    aligned = build_cues_via_whisperx(
        media,
        narration_text=text,
        allow_asr=True,
    )
    if aligned:
        return normalize_non_overlapping_cues(aligned)

    if prefer_audio:
        return []
    if not text:
        return []
    duration_ms = int((media.metadata or {}).get("duration_ms") or 0)
    return normalize_non_overlapping_cues(_proportional_fallback_cues(text, duration_ms))


def enrich_subtitles_from_audio(
    store: MemoryStore,
    timeline: EditTimeline,
    plan: VideoPlan | None = None,
) -> EditTimeline:
    """新模型：字幕已由镜内 Shot.subtitles 投影进 timeline，直接返回（无补齐/降级）。"""
    del store, plan
    return timeline
