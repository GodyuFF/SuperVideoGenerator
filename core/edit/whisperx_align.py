"""WhisperX 强制对齐：已知旁白文案 → 句级 subtitle_cues（仅 CUDA）。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from core.edit.whisperx_settings import get_whisperx_settings
from core.llm.tools.shared.media_list import resolve_media_access
from core.tts.text import split_string_by_punctuations

logger = logging.getLogger("core.edit.whisperx_align")

# (language, device, align_model) → (model, metadata)
_ALIGN_MODEL_CACHE: dict[tuple[str, str, str], tuple[Any, dict[str, Any]]] = {}


def is_whisperx_available() -> bool:
    """检测 whisperx 可导入且当前环境有 CUDA。"""
    try:
        import torch
        import whisperx  # noqa: F401
    except Exception:
        return False
    try:
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def resolve_local_audio_path(media: Any) -> Path | None:
    """从 MediaAsset / 临时对象解析可读的本地音频路径。"""
    url = str(getattr(media, "url", "") or "").strip()
    if not url:
        return None
    access = resolve_media_access(url)
    file_path = str(access.get("file_path") or "").strip()
    if file_path:
        path = Path(file_path)
        if path.is_file():
            return path.resolve()
    path = Path(url)
    if path.is_file():
        return path.resolve()
    return None


def _duration_sec_for_media(media: Any, audio_path: Path) -> float:
    """优先 metadata.duration_ms，否则用 whisperx 采样探测。"""
    meta = getattr(media, "metadata", None) or {}
    try:
        duration_ms = int(meta.get("duration_ms") or 0)
    except (TypeError, ValueError):
        duration_ms = 0
    if duration_ms > 0:
        return max(duration_ms / 1000.0, 0.1)
    try:
        import whisperx

        audio = whisperx.load_audio(str(audio_path))
        # whisperx 固定 16kHz
        return max(float(len(audio)) / 16000.0, 0.1)
    except Exception:
        return 0.1


def _build_seed_segments(text: str, duration_sec: float) -> list[dict[str, Any]]:
    """按标点拆句并赋予比例时间窗，供 WhisperX 精修。"""
    sentences = [s.strip() for s in split_string_by_punctuations(text) if s.strip()]
    if not sentences:
        sentences = [text.strip()]
    total_chars = sum(len(s) for s in sentences) or 1
    cursor = 0.0
    segments: list[dict[str, Any]] = []
    for index, sentence in enumerate(sentences):
        if index == len(sentences) - 1:
            end = duration_sec
        else:
            share = len(sentence) / total_chars
            end = min(cursor + max(duration_sec * share, 0.05), duration_sec)
        segments.append({"text": sentence, "start": cursor, "end": max(end, cursor + 0.05)})
        cursor = end
    return segments


def _get_align_model(language: str, device: str, align_model: str) -> tuple[Any, dict[str, Any]]:
    """加载并对齐模型做进程内缓存。"""
    key = (language, device, align_model)
    cached = _ALIGN_MODEL_CACHE.get(key)
    if cached is not None:
        return cached
    import whisperx

    kwargs: dict[str, Any] = {"language_code": language, "device": device}
    if align_model:
        kwargs["model_name"] = align_model
    model_a, metadata = whisperx.load_align_model(**kwargs)
    _ALIGN_MODEL_CACHE[key] = (model_a, metadata)
    return model_a, metadata


def _cues_from_aligned_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将 WhisperX 对齐后的 segment 转为 subtitle_cues。"""
    cues: list[dict[str, Any]] = []
    for seg in segments:
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        try:
            start_ms = int(float(seg.get("start", 0)) * 1000)
            end_ms = int(float(seg.get("end", 0)) * 1000)
        except (TypeError, ValueError):
            continue
        if end_ms <= start_ms:
            continue
        cues.append(
            {
                "text": text,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "character": "",
                "color": "",
                "source": "whisperx",
            }
        )
    return cues


def align_text_to_audio(
    audio_path: str | Path,
    text: str,
    *,
    language: str | None = None,
    duration_sec: float | None = None,
) -> list[dict[str, Any]]:
    """将已知文案强制对齐到音频，返回句级 cue；失败返回空列表。"""
    cleaned = (text or "").strip()
    path = Path(audio_path)
    if not cleaned or not path.is_file():
        return []
    if not is_whisperx_available():
        return []

    settings = get_whisperx_settings()
    lang = (language or settings.language or "zh").strip() or "zh"
    device = "cuda"
    try:
        import whisperx

        audio = whisperx.load_audio(str(path))
        if duration_sec is None or duration_sec <= 0:
            duration_sec = max(float(len(audio)) / 16000.0, 0.1)
        seed = _build_seed_segments(cleaned, float(duration_sec))
        model_a, metadata = _get_align_model(lang, device, (settings.align_model or "").strip())
        result = whisperx.align(
            seed,
            model_a,
            metadata,
            audio,
            device,
            return_char_alignments=False,
        )
        segments = list(result.get("segments") or [])
        cues = _cues_from_aligned_segments(segments)
        if cues:
            logger.info(
                "whisperx aligned cues=%s audio=%s language=%s",
                len(cues),
                path.name,
                lang,
            )
        return cues
    except Exception:
        logger.exception("whisperx align failed audio=%s", path)
        return []


def transcribe_audio_to_cues(
    audio_path: str | Path,
    *,
    language: str | None = None,
) -> list[dict[str, Any]]:
    """无参考文案时用 WhisperX ASR 转写音频为句级 cue（仅 CUDA）。"""
    path = Path(audio_path)
    if not path.is_file() or not is_whisperx_available():
        return []
    settings = get_whisperx_settings()
    lang = (language or settings.language or "zh").strip() or "zh"
    model_name = (settings.model or "base").strip() or "base"
    device = "cuda"
    try:
        import whisperx

        audio = whisperx.load_audio(str(path))
        model = whisperx.load_model(model_name, device, compute_type="float16")
        result = model.transcribe(audio, batch_size=8, language=lang)
        segments = list(result.get("segments") or [])
        # 有对齐模型时对转写结果再对齐，精度更好
        try:
            model_a, metadata = _get_align_model(
                lang, device, (settings.align_model or "").strip()
            )
            aligned = whisperx.align(
                segments,
                model_a,
                metadata,
                audio,
                device,
                return_char_alignments=False,
            )
            segments = list(aligned.get("segments") or segments)
        except Exception:
            logger.exception("whisperx post-align after asr failed audio=%s", path.name)
        cues = _cues_from_aligned_segments(segments)
        for cue in cues:
            cue["source"] = "whisperx_asr"
        if cues:
            logger.info(
                "whisperx asr cues=%s audio=%s language=%s model=%s",
                len(cues),
                path.name,
                lang,
                model_name,
            )
        return cues
    except Exception:
        logger.exception("whisperx asr failed audio=%s", path)
        return []


def build_cues_via_whisperx(
    media: Any,
    *,
    narration_text: str = "",
    align_fn: Callable[..., list[dict[str, Any]]] | None = None,
    allow_asr: bool = True,
) -> list[dict[str, Any]]:
    """对 media 尝试 WhisperX：有文案则强制对齐，否则 ASR 转写。"""
    text = narration_text.strip() or str(
        (getattr(media, "metadata", None) or {}).get("narration_text") or ""
    ).strip()
    audio_path = resolve_local_audio_path(media)
    if audio_path is None:
        return []
    if not is_whisperx_available() and align_fn is None:
        return []
    if text:
        duration_sec = _duration_sec_for_media(media, audio_path)
        runner = align_fn or align_text_to_audio
        aligned = runner(audio_path, text, duration_sec=duration_sec)
        if aligned:
            return aligned
    if allow_asr and align_fn is None:
        return transcribe_audio_to_cues(audio_path)
    return []


def clear_align_model_cache() -> None:
    """清空对齐模型缓存（测试用）。"""
    _ALIGN_MODEL_CACHE.clear()
