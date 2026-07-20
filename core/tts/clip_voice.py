"""配音幕 clip 音色解析。"""

from __future__ import annotations

from core.models.entities import ShotAudioClip, TextAssetType
from core.store.memory import MemoryStore
from core.tts.engine import TtsRuntimeConfig


def resolve_voice_act_voice_name(
    store: MemoryStore | None,
    clip: ShotAudioClip,
    runtime: TtsRuntimeConfig,
) -> str:
    """解析 clip 实际 TTS 音色：显式 voice > 关联角色 tts_voice > 项目默认旁白。"""
    explicit = str(clip.voice or "").strip()
    if explicit:
        return explicit
    ref = str(clip.character_ref or "").strip()
    if store and ref:
        asset = store.text_assets.get(ref)
        if asset and asset.type == TextAssetType.CHARACTER:
            from core.assets.service import apply_character_tts_voice

            content = dict(asset.content or {})
            normalized = apply_character_tts_voice(content)
            voice = str(normalized.get("tts_voice") or "").strip()
            if voice:
                return voice
    return runtime.voice_name
