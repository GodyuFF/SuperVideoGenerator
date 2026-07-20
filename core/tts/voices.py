"""TTS 音色列表与解析。"""

from __future__ import annotations

import json
from pathlib import Path

_AZURE_VOICES_DATA_FILE = Path(__file__).resolve().parent / "data" / "azure_voices.json"
_azure_voices_cache: list[dict] | None = None

NO_VOICE_NAME = "no-voice"
_NO_VOICE_ALIASES = {NO_VOICE_NAME, "none"}

OPENAI_TTS_VOICES = (
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "onyx",
    "nova",
    "sage",
    "shimmer",
)


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


def get_openai_voices() -> list[str]:
    """OpenAI TTS 预置音色列表。"""
    return list(OPENAI_TTS_VOICES)


def get_azure_v2_voices(filter_locals: list[str] | None = None) -> list[str]:
    """Azure Speech v2 音色（在 Edge 音色名中插入 -V2 标记）。"""
    return [
        v.replace("-Female", "-V2-Female").replace("-Male", "-V2-Male")
        for v in get_all_azure_voices(filter_locals)
    ]


def get_voices_for_provider(provider: str, locale: str | None = None) -> list[str]:
    """按 TTS 服务商与语言区域返回当前可加载的音色列表。"""
    p = (provider or "edge").strip().lower()
    filter_locals = [locale] if locale else None
    if p == "openai":
        return get_openai_voices()
    if p == "siliconflow":
        return get_siliconflow_voices()
    if p == "gemini":
        return get_gemini_voices()
    if p == "mimo":
        return get_mimo_voices()
    if p == "azure_v2":
        return get_azure_v2_voices(filter_locals)
    return get_all_azure_voices(filter_locals)


def voice_allowed_for_provider(
    voice_name: str,
    provider: str,
    locale: str | None = None,
) -> bool:
    """判断音色是否属于指定 TTS 服务商的可选集合。"""
    voice = str(voice_name or "").strip()
    if not voice:
        return False
    return voice in get_voices_for_provider(provider, locale)


def _gender_prefers_female(gender: str) -> bool | None:
    """从角色 gender 字段推断音色性别偏好；无法推断时返回 None。"""
    g = str(gender or "").strip().lower()
    if not g or g in ("未指定", "unknown", "n/a"):
        return None
    if any(token in g for token in ("女", "female", "girl", "woman")):
        return True
    if any(token in g for token in ("男", "male", "boy", "man")):
        return False
    return None


def resolve_character_tts_voice(
    voice_name: str | None,
    *,
    gender: str = "",
    provider: str = "edge",
    locale: str | None = "zh-CN",
    default_voice: str = "",
) -> str:
    """将角色 tts_voice 解析为当前 TTS 配置允许的值；空值时按性别或默认音色推断。"""
    voice = str(voice_name or "").strip()
    candidates = get_voices_for_provider(provider, locale)
    if not candidates:
        return voice or default_voice or resolve_default_voice(
            provider, default_voice, locale or "zh-CN"
        )

    if voice and voice in candidates:
        return voice

    fallback = (
        default_voice
        if default_voice in candidates
        else candidates[0]
    )

    if voice:
        return fallback

    prefers_female = _gender_prefers_female(gender)
    if prefers_female is True:
        for candidate in candidates:
            if candidate.endswith("-Female"):
                return candidate
        for candidate in candidates:
            if candidate in ("nova", "shimmer", "coral"):
                return candidate
    elif prefers_female is False:
        for candidate in candidates:
            if candidate.endswith("-Male"):
                return candidate
        for candidate in candidates:
            if candidate in ("onyx", "echo", "fable", "alloy"):
                return candidate
    return fallback


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
