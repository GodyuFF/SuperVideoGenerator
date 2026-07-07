"""tts_agent tools 注册。"""

from core.llm.tools.register_helpers import register_handlers
from core.llm.tools.registry import ToolRegistry
from core.llm.tools.tts.handler import HANDLERS as TTS_HANDLERS

_TTS_META: dict[str, tuple[str, str, str, str]] = {
    "extract_narration": ("tts_agent", "write_pipeline", "tts.extract_narration", "从计划稿提取旁白"),
    "synthesize": ("tts_agent", "write_pipeline", "tts.synthesize", "合成 TTS 音频"),
    "list_audio": ("tts_agent", "read", "tts.list_audio", "列出配音资产"),
}


def register_tts_tools(registry: ToolRegistry) -> None:
    register_handlers(registry, TTS_HANDLERS, _TTS_META)
