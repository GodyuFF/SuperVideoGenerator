"""core/tts 引擎与文本工具单元测试。"""

from core.tts.text import convert_rate_to_percent, split_string_by_punctuations
from core.tts.voices import (
    get_all_voices,
    is_gemini_voice,
    is_mimo_voice,
    is_no_voice,
    is_siliconflow_voice,
    parse_voice_name,
    resolve_default_voice,
)


def test_convert_rate_to_percent():
    assert convert_rate_to_percent(1.0) == "+0%"
    assert convert_rate_to_percent(1.2) == "+20%"
    assert convert_rate_to_percent(0.8) == "-20%"


def test_split_string_by_punctuations():
    parts = split_string_by_punctuations("你好，世界。测试")
    assert len(parts) >= 2
    assert "你好" in parts[0]


def test_voice_name_parsing():
    assert parse_voice_name("zh-CN-XiaoxiaoNeural-Female") == "zh-CN-XiaoxiaoNeural"
    assert is_siliconflow_voice("siliconflow:model:alex-Male")
    assert is_gemini_voice("gemini:Zephyr-Female")
    assert is_mimo_voice("mimo:冰糖-Female")
    assert is_no_voice("no-voice")


def test_get_all_voices_includes_edge_and_cloud():
    voices = get_all_voices("zh-CN")
    assert any("zh-CN" in v for v in voices)
    assert any(v.startswith("siliconflow:") for v in voices)
    assert "no-voice" in voices


def test_resolve_default_voice_edge():
    voice = resolve_default_voice("edge", "", "zh-CN")
    assert "zh-CN" in voice
