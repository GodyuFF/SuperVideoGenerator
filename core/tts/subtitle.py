"""SubMaker 兼容层与字幕时间轴工具。"""

from __future__ import annotations

import math
from typing import Any

from edge_tts import SubMaker

from core.tts.text import split_string_by_punctuations


def mktimestamp(time_unit: float) -> str:
    hour = math.floor(time_unit / 10**7 / 3600)
    minute = math.floor((time_unit / 10**7 / 60) % 60)
    seconds = (time_unit / 10**7) % 60
    return f"{hour:02d}:{minute:02d}:{seconds:06.3f}"


def ensure_legacy_submaker_fields(sub_maker: SubMaker) -> SubMaker:
    if not hasattr(sub_maker, "subs"):
        sub_maker.subs = []
    if not hasattr(sub_maker, "offset"):
        sub_maker.offset = []
    return sub_maker


def populate_legacy_submaker_with_full_text(
    sub_maker: SubMaker,
    text: str,
    audio_duration_seconds: float,
) -> SubMaker:
    sub_maker = ensure_legacy_submaker_fields(sub_maker)
    sub_maker.subs = []
    sub_maker.offset = []

    normalized_text = (text or "").strip()
    if not normalized_text:
        return sub_maker

    audio_duration_100ns = max(int(audio_duration_seconds * 10000000), 1)
    sentences = split_string_by_punctuations(normalized_text)
    if not sentences:
        sentences = [normalized_text]

    total_chars = sum(len(sentence) for sentence in sentences)
    if total_chars <= 0:
        sub_maker.subs.append(normalized_text)
        sub_maker.offset.append((0, audio_duration_100ns))
        return sub_maker

    current_offset = 0
    for index, sentence in enumerate(sentences):
        cleaned_sentence = sentence.strip()
        if not cleaned_sentence:
            continue
        if index == len(sentences) - 1:
            sentence_end = audio_duration_100ns
        else:
            sentence_chars = len(cleaned_sentence)
            sentence_duration = max(
                int(audio_duration_100ns * (sentence_chars / total_chars)),
                1,
            )
            sentence_end = min(current_offset + sentence_duration, audio_duration_100ns)
        sub_maker.subs.append(cleaned_sentence)
        sub_maker.offset.append((current_offset, sentence_end))
        current_offset = sentence_end
    return sub_maker


def submaker_cues_to_clips(
    sub_maker: SubMaker,
    *,
    offset_ms: int = 0,
    shot_id: str = "",
) -> list[dict[str, Any]]:
    """将 SubMaker 转为 EditClip 兼容的字典列表（毫秒时间轴）。"""
    clips: list[dict[str, Any]] = []
    if hasattr(sub_maker, "cues") and sub_maker.cues:
        for cue in sub_maker.cues:
            start_ms = offset_ms + int(cue.start.total_seconds() * 1000)
            end_ms = offset_ms + int(cue.end.total_seconds() * 1000)
            text = str(getattr(cue, "text", "") or "").strip()
            if not text or end_ms <= start_ms:
                continue
            clips.append(
                {
                    "track": "subtitle",
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "label": text,
                    "metadata": {"shot_id": shot_id} if shot_id else {},
                }
            )
        return clips

    legacy_offsets = getattr(sub_maker, "offset", [])
    legacy_subs = getattr(sub_maker, "subs", [])
    for text, (start_100ns, end_100ns) in zip(legacy_subs, legacy_offsets):
        start_ms = offset_ms + int(start_100ns / 10000)
        end_ms = offset_ms + int(end_100ns / 10000)
        label = str(text).strip()
        if not label or end_ms <= start_ms:
            continue
        clips.append(
            {
                "track": "subtitle",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "label": label,
                "metadata": {"shot_id": shot_id} if shot_id else {},
            }
        )
    return clips


def normalize_non_overlapping_cues(
    cues: list[dict[str, Any]],
    *,
    min_duration_ms: int = 1,
) -> list[dict[str, Any]]:
    """按 start_ms 排序并截断重叠区间，保证同一时刻仅一条可读字幕。

    策略：保留各条原有起点；若与后一条重叠，则将较早条目的 end_ms 截到后一条 start_ms。
    截断后时长不足 ``min_duration_ms`` 的条目丢弃。
    """
    prepared: list[dict[str, Any]] = []
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        text = str(cue.get("text") or cue.get("label") or "").strip()
        if not text:
            continue
        try:
            start_ms = int(cue.get("start_ms", 0))
            end_ms = int(cue.get("end_ms", 0))
        except (TypeError, ValueError):
            continue
        if end_ms <= start_ms:
            continue
        prepared.append({**cue, "text": text, "start_ms": start_ms, "end_ms": end_ms})

    prepared.sort(key=lambda c: (int(c["start_ms"]), int(c["end_ms"])))
    for i in range(len(prepared) - 1):
        next_start = int(prepared[i + 1]["start_ms"])
        if int(prepared[i]["end_ms"]) > next_start:
            prepared[i]["end_ms"] = next_start
    return [
        c
        for c in prepared
        if int(c["end_ms"]) - int(c["start_ms"]) >= min_duration_ms
    ]


def subtitle_cues_from_submaker(sub_maker: SubMaker) -> list[dict[str, Any]]:
    """将 SubMaker 序列化为可持久化的 cue 列表（保证条目时间不重叠）。"""
    return normalize_non_overlapping_cues(
        [
            {
                "start_ms": int(c["start_ms"]),
                "end_ms": int(c["end_ms"]),
                "text": str(c["label"]),
                "character": "",
                "color": "",
            }
            for c in submaker_cues_to_clips(sub_maker)
        ]
    )


def subtitle_clips_from_cues(
    cues: list[dict[str, Any]],
    *,
    offset_ms: int = 0,
    shot_id: str = "",
) -> list[dict[str, Any]]:
    """metadata.subtitle_cues → EditClip 兼容 dict 列表。"""
    clips: list[dict[str, Any]] = []
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        text = str(cue.get("text") or cue.get("label") or "").strip()
        if not text:
            continue
        try:
            start_ms = offset_ms + int(cue.get("start_ms", 0))
            end_ms = offset_ms + int(cue.get("end_ms", 0))
        except (TypeError, ValueError):
            continue
        if end_ms <= start_ms:
            continue
        clips.append(
            {
                "track": "subtitle",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "label": text,
                "metadata": {"shot_id": shot_id} if shot_id else {},
            }
        )
    return clips
