"""TTS 音色按服务商过滤与角色音色解析测试。"""

from core.tts.voices import (
    get_voices_for_provider,
    resolve_character_tts_voice,
    voice_allowed_for_provider,
)


def test_get_voices_for_provider_edge_zh_cn():
    voices = get_voices_for_provider("edge", "zh-CN")
    assert voices
    assert all(not v.startswith("siliconflow:") for v in voices)
    assert any("Xiaoxiao" in v for v in voices)


def test_get_voices_for_provider_openai():
    voices = get_voices_for_provider("openai", "zh-CN")
    assert "alloy" in voices
    assert "nova" in voices


def test_get_voices_for_provider_siliconflow():
    voices = get_voices_for_provider("siliconflow", "zh-CN")
    assert voices
    assert all(v.startswith("siliconflow:") for v in voices)


def test_voice_allowed_for_provider():
    voices = get_voices_for_provider("edge", "zh-CN")
    assert voice_allowed_for_provider(voices[0], "edge", "zh-CN")
    assert not voice_allowed_for_provider("siliconflow:x:y-Female", "edge", "zh-CN")


def test_resolve_character_tts_voice_from_gender_female():
    voices = get_voices_for_provider("edge", "zh-CN")
    resolved = resolve_character_tts_voice(
        "",
        gender="女",
        provider="edge",
        locale="zh-CN",
        default_voice=voices[0],
    )
    assert resolved in voices
    assert resolved.endswith("-Female")


def test_resolve_character_tts_voice_keeps_valid():
    voices = get_voices_for_provider("edge", "zh-CN")
    pick = voices[0]
    assert resolve_character_tts_voice(
        pick,
        gender="男",
        provider="edge",
        locale="zh-CN",
        default_voice=pick,
    ) == pick


def test_resolve_character_tts_voice_invalid_falls_back():
    voices = get_voices_for_provider("edge", "zh-CN")
    resolved = resolve_character_tts_voice(
        "invalid-voice-name",
        gender="",
        provider="edge",
        locale="zh-CN",
        default_voice=voices[0],
    )
    assert resolved in voices
