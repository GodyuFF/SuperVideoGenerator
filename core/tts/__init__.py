"""文字转语音（TTS）多引擎合成。"""

from core.tts.duration import get_audio_duration
from core.tts.engine import synthesize_speech
from core.tts.errors import TtsAbortError, TtsSynthesisError
from core.tts.voices import get_all_voices, parse_voice_name

__all__ = [
    "TtsAbortError",
    "TtsSynthesisError",
    "get_all_voices",
    "get_audio_duration",
    "parse_voice_name",
    "synthesize_speech",
]
