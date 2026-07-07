"""TTS 音色列表与解析。"""

from __future__ import annotations

import json
from pathlib import Path

_AZURE_VOICES_DATA_FILE = Path(__file__).resolve().parent / "data" / "azure_voices.json"
_azure_voices_cache: list[dict] | None = None

NO_VOICE_NAME = "no-voice"
_NO_VOICE_ALIASES = {NO_VOICE_NAME, "none"}


def _load_azure_voices() -> list[dict]:
    global _azure_voices_cache
    if _azure_voices_cache is None:
        with open(_AZURE_VOICES_DATA_FILE, encoding="utf-8") as f:
            _azure_voices_cache = json.load(f)
    return _azure_voices_cache


def get_all_azure_voices(filter_locals: list[str] | None = None) -> list[str]:
    voices: list[str] = []
    for item in _load_azure_voices():
        name = item["name"]
        gender = item["gender"]
        if filter_locals and any(
            name.lower().startswith(fl.lower()) for fl in filter_locals
        ):
            voices.append(f"{name}-{gender}")
        elif not filter_locals:
            voices.append(f"{name}-{gender}")
    voices.sort()
    return voices


def get_siliconflow_voices() -> list[str]:
    voices_with_gender = [
        ("FunAudioLLM/CosyVoice2-0.5B", "alex", "Male"),
        ("FunAudioLLM/CosyVoice2-0.5B", "anna", "Female"),
        ("FunAudioLLM/CosyVoice2-0.5B", "bella", "Female"),
        ("FunAudioLLM/CosyVoice2-0.5B", "benjamin", "Male"),
        ("FunAudioLLM/CosyVoice2-0.5B", "charles", "Male"),
        ("FunAudioLLM/CosyVoice2-0.5B", "claire", "Female"),
        ("FunAudioLLM/CosyVoice2-0.5B", "david", "Male"),
        ("FunAudioLLM/CosyVoice2-0.5B", "diana", "Female"),
    ]
    return [
        f"siliconflow:{model}:{voice}-{gender}"
        for model, voice, gender in voices_with_gender
    ]


def get_gemini_voices() -> list[str]:
    voices_with_gender = [
        ("Zephyr", "Female"),
        ("Puck", "Male"),
        ("Charon", "Male"),
        ("Kore", "Female"),
        ("Fenrir", "Male"),
        ("Aoede", "Female"),
        ("Thalia", "Female"),
        ("Sage", "Male"),
        ("Echo", "Female"),
        ("Harmony", "Female"),
        ("Lux", "Female"),
        ("Nova", "Female"),
        ("Vale", "Male"),
        ("Orion", "Male"),
        ("Atlas", "Male"),
    ]
    return [f"gemini:{voice}-{gender}" for voice, gender in voices_with_gender]


def get_mimo_voices() -> list[str]:
    voices_with_gender = [
        ("mimo_default", "Female"),
        ("冰糖", "Female"),
        ("茉莉", "Female"),
        ("苏打", "Male"),
        ("白桦", "Male"),
        ("Mia", "Female"),
        ("Chloe", "Female"),
        ("Milo", "Male"),
        ("Dean", "Male"),
    ]
    return [f"mimo:{voice}-{gender}" for voice, gender in voices_with_gender]


def get_all_voices(locale: str | None = None) -> list[str]:
    filter_locals = [locale] if locale else None
    voices = get_all_azure_voices(filter_locals)
    voices.extend(get_siliconflow_voices())
    voices.extend(get_gemini_voices())
    voices.extend(get_mimo_voices())
    voices.append(NO_VOICE_NAME)
    return sorted(set(voices))


def parse_voice_name(name: str) -> str:
    return name.replace("-Female", "").replace("-Male", "").strip()


def is_azure_v2_voice(voice_name: str) -> str:
    voice_name = parse_voice_name(voice_name)
    if voice_name.endswith("-V2"):
        return voice_name.replace("-V2", "").strip()
    return ""


def is_siliconflow_voice(voice_name: str) -> bool:
    return voice_name.startswith("siliconflow:")


def is_gemini_voice(voice_name: str) -> bool:
    return voice_name.startswith("gemini:")


def is_mimo_voice(voice_name: str) -> bool:
    return voice_name.startswith("mimo:")


def is_no_voice(voice_name: str | None) -> bool:
    return str(voice_name or "").strip().lower() in _NO_VOICE_ALIASES


def resolve_default_voice(provider: str, default_voice: str, default_language: str) -> str:
    voice = (default_voice or "").strip()
    if voice:
        return voice
    lang = (default_language or "zh-CN").strip()
    if provider == "openai":
        return "alloy"
    candidates = get_all_azure_voices([lang])
    if candidates:
        for preferred in ("XiaoxiaoNeural", "YunxiNeural"):
            for candidate in candidates:
                if preferred in candidate:
                    return candidate
        return candidates[0]
    return "zh-CN-XiaoxiaoNeural-Female"
