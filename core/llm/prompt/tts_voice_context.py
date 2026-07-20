"""将当前 TTS 配置与可选音色注入 script_agent 动态上下文。"""

from __future__ import annotations

from typing import Any


def build_tts_voice_context() -> dict[str, Any]:
    """读取全局 TTS 设置，返回子 Agent 可选音色上下文。"""
    from core.llm.tools.tts.settings import get_tts_manager
    from core.tts.voices import get_voices_for_provider

    settings = get_tts_manager().get_settings()
    voices = get_voices_for_provider(settings.provider, settings.default_language)
    return {
        "tts_provider": settings.provider,
        "tts_default_language": settings.default_language,
        "tts_default_voice": settings.default_voice,
        "tts_available_voices": voices,
    }


def format_tts_voice_hint_block(ctx: dict[str, Any]) -> str:
    """格式化为行动执行 store_context 附录文本。"""
    voices = ctx.get("tts_available_voices") or []
    if not voices:
        return ""
    provider = str(ctx.get("tts_provider", "")).strip()
    language = str(ctx.get("tts_default_language", "")).strip()
    default_voice = str(ctx.get("tts_default_voice", "")).strip()
    lines = [
        f"TTS 配置：provider={provider} language={language} default_voice={default_voice}",
        "可选音色（create_character 的 content.tts_voice 必须从中选择）：",
    ]
    for voice in voices[:40]:
        lines.append(f"- {voice}")
    if len(voices) > 40:
        lines.append(f"- …共 {len(voices)} 项，未全部列出")
    return "\n".join(lines) + "\n"
