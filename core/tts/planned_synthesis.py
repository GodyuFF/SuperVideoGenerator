"""按分镜规划时间轴强约束合成 TTS 音频。"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from edge_tts import SubMaker

from core.edit.voice_speaker import voice_clip_speaker_kind
from core.models.entities import Shot, ShotAudioClip
from core.store.memory import MemoryStore
from core.tts.clip_voice import resolve_voice_act_voice_name
from core.tts.duration import duration_ms_from_target
from core.tts.engine import TtsRuntimeConfig, build_runtime_config, synthesize_speech
from core.tts.silent import generate_silent_audio
from core.tts.subtitle import normalize_non_overlapping_cues, subtitle_cues_from_submaker

logger = logging.getLogger("core.tts.planned_synthesis")

TOLERANCE_MS = 150
MAX_RATE_ATTEMPTS = 3


@dataclass
class PlannedSynthesisResult:
    """单镜规划约束合成结果。"""

    duration_ms: int
    subtitle_cues: list[dict[str, Any]]
    duration_drift_ms: int = 0
    used_planned_timeline: bool = True


def _voice_clips(shot: Shot) -> list[ShotAudioClip]:
    """返回镜内全部 voice 音频 clip（按起点排序）。"""
    clips: list[ShotAudioClip] = []
    for track in shot.audio_tracks:
        if track.kind == "voice":
            clips.extend(track.clips)
    return sorted(clips, key=lambda c: c.start_ms)


def _shot_voice_text(shot: Shot) -> str:
    """拼接镜内 voice clip 文案。"""
    return "".join(c.text.strip() for c in _voice_clips(shot) if c.text.strip())


def _synthesize_segment_with_rate(
    text: str,
    output_path: Path,
    runtime: TtsRuntimeConfig,
    *,
    target_ms: int,
    base_rate: float,
    voice_name: str | None = None,
) -> tuple[SubMaker | None, int]:
    """合成单段并二分调整语速以逼近目标时长。"""
    if not text.strip():
        generate_silent_audio(max(target_ms, 100) / 1000.0, str(output_path))
        return None, duration_ms_from_target(output_path)

    low, high = max(0.5, base_rate * 0.6), min(2.0, base_rate * 1.6)
    best_sub: SubMaker | None = None
    best_ms = 0
    best_drift = 10**9

    for attempt in range(MAX_RATE_ATTEMPTS):
        rate = (low + high) / 2.0 if attempt else base_rate
        sub = synthesize_speech(
            text,
            str(output_path),
            runtime,
            voice_rate=rate,
            voice_name=voice_name,
        )
        actual_ms = duration_ms_from_target(sub or output_path)
        drift = abs(actual_ms - target_ms)
        if drift < best_drift:
            best_drift = drift
            best_ms = actual_ms
            best_sub = sub
        if drift <= TOLERANCE_MS:
            return sub, actual_ms
        if actual_ms > target_ms:
            low = rate
        else:
            high = rate

    return best_sub, best_ms


def _concat_audio_files(segment_files: list[Path], output_path: Path) -> int:
    """使用 ffmpeg 拼接多段 mp3 并返回总时长毫秒。"""
    from core.tts.duration import duration_ms_from_target
    from core.tts.ffmpeg_util import resolve_ffmpeg_binary

    valid = [p for p in segment_files if p.is_file() and p.stat().st_size > 0]
    if not valid:
        return 0
    if len(valid) == 1:
        valid[0].replace(output_path)
        return duration_ms_from_target(output_path)

    ffmpeg = resolve_ffmpeg_binary()
    list_file = output_path.parent / "tts_concat_list.txt"
    lines = [f"file '{p.resolve().as_posix()}'" for p in valid]
    list_file.write_text("\n".join(lines), encoding="utf-8")
    import subprocess

    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not output_path.is_file():
        raise RuntimeError((result.stderr or result.stdout or "ffmpeg concat failed").strip())
    return duration_ms_from_target(output_path)


def synthesize_shot_with_plan(
    shot: Shot,
    output_path: Path,
    runtime: TtsRuntimeConfig,
    *,
    store: MemoryStore | None = None,
) -> PlannedSynthesisResult:
    """按镜内 voice 音频 clip 合成单镜配音（多段则按时间窗拼接静音间隔）。"""
    voice_clips = [c for c in _voice_clips(shot) if c.text.strip()]
    if not voice_clips:
        text = _shot_voice_text(shot)
        sub = synthesize_speech(text, str(output_path), runtime)
        duration_ms = duration_ms_from_target(sub or output_path)
        cues = normalize_non_overlapping_cues(
            subtitle_cues_from_submaker(sub) if sub else []
        )
        return PlannedSynthesisResult(
            duration_ms=duration_ms,
            subtitle_cues=cues,
            used_planned_timeline=False,
        )

    # 单段：直接合成，cue 用 clip 文本
    if len(voice_clips) == 1:
        clip = voice_clips[0]
        voice_name = resolve_voice_act_voice_name(store, clip, runtime)
        sub = synthesize_speech(
            clip.text.strip(),
            str(output_path),
            runtime,
            voice_name=voice_name,
        )
        duration_ms = duration_ms_from_target(sub or output_path)
        cues = [
            {
                "start_ms": 0,
                "end_ms": duration_ms,
                "text": clip.text.strip(),
                "character": "",
                "color": "",
                "source": "clip",
            }
        ]
        return PlannedSynthesisResult(
            duration_ms=duration_ms,
            subtitle_cues=cues,
            used_planned_timeline=True,
        )

    # 多段：按 clip 时间窗拼接（含段间静音），cue 用各 clip 区间
    planned_total = max(c.end_ms for c in voice_clips)
    segment_files: list[Path] = []
    subtitle_cues: list[dict[str, Any]] = []
    tmp_dir = Path(tempfile.mkdtemp(prefix="svf_tts_plan_"))
    try:
        cursor = 0
        seg_index = 0
        for clip in voice_clips:
            # 段前静音
            if clip.start_ms > cursor:
                gap_path = tmp_dir / f"gap_{seg_index}.mp3"
                generate_silent_audio((clip.start_ms - cursor) / 1000.0, str(gap_path))
                segment_files.append(gap_path)
                seg_index += 1
            seg_path = tmp_dir / f"seg_{seg_index}.mp3"
            target_ms = max(clip.end_ms - clip.start_ms, 0)
            voice_name = resolve_voice_act_voice_name(store, clip, runtime)
            _synthesize_segment_with_rate(
                clip.text.strip(),
                seg_path,
                runtime,
                target_ms=target_ms,
                base_rate=runtime.voice_rate,
                voice_name=voice_name,
            )
            segment_files.append(seg_path)
            seg_index += 1
            subtitle_cues.append(
                {
                    "start_ms": clip.start_ms,
                    "end_ms": clip.end_ms,
                    "text": clip.text.strip(),
                    "character": "",
                    "color": "",
                    "source": "clip",
                }
            )
            cursor = clip.end_ms

        _concat_audio_files(segment_files, output_path)
        duration_ms = duration_ms_from_target(output_path)
        if duration_ms <= 0:
            duration_ms = planned_total
        drift = abs(duration_ms - planned_total)
        return PlannedSynthesisResult(
            duration_ms=duration_ms,
            subtitle_cues=normalize_non_overlapping_cues(subtitle_cues),
            duration_drift_ms=drift,
            used_planned_timeline=True,
        )
    finally:
        for path in segment_files:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            tmp_dir.rmdir()
        except OSError:
            pass


def build_voice_segments_from_shot(shot: Shot) -> list[dict[str, Any]]:
    """从镜内 voice clip 提取语音段供 TTS extract 使用。"""
    segments: list[dict[str, Any]] = []
    for clip in _voice_clips(shot):
        text = clip.text.strip()
        if not text:
            continue
        segments.append(
            {
                "start_ms": clip.start_ms,
                "end_ms": clip.end_ms,
                "target_ms": clip.end_ms - clip.start_ms,
                "text": text,
                "character_ref": str(clip.character_ref or "").strip(),
                "speaker_kind": voice_clip_speaker_kind(clip),
            }
        )
    return segments
