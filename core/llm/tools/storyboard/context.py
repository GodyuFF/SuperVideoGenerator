"""storyboard_agent load_context 结构化载荷。"""

from __future__ import annotations

from typing import Any

from core.edit.voice_speaker import build_available_voice_speakers
from core.llm.tools.image.scan import build_scan_text_assets_payload
from core.llm.tools.shared.linked_assets import (
    build_assets_with_images_from_scan,
    build_plots_for_script,
)
from core.models.entities import TextAssetType
from core.models.image_text_asset import CharacterContent, normalize_image_text_content
from core.store.memory import MemoryStore


def _voice_summary_from_assets(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从角色资产提取 TTS 音色摘要。"""
    voices: list[dict[str, Any]] = []
    for asset in assets:
        if asset.get("type") != TextAssetType.CHARACTER.value:
            continue
        content_raw = asset.get("content") or {}
        try:
            content = CharacterContent.model_validate(
                normalize_image_text_content(TextAssetType.CHARACTER, content_raw)
            )
            voice = str(content.tts_voice or "").strip()
            if voice:
                voices.append(
                    {
                        "asset_id": asset.get("id"),
                        "name": asset.get("name"),
                        "tts_voice": voice,
                    }
                )
        except Exception:
            continue
    return voices


def build_storyboard_context_payload(
    store: MemoryStore,
    script_id: str,
) -> dict[str, Any]:
    """剧本正文、剧情段落、图文资产与已链接图片，供分镜设计使用。"""
    script = store.get_script(script_id)
    if script is None:
        raise ValueError(f"剧本 {script_id} 不存在")

    payload = build_scan_text_assets_payload(store, script_id)
    script_block = dict(payload.get("script") or {})
    script_block["content_md"] = script.content_md or ""
    script_block["duration_sec"] = int(script.duration_sec or 0)
    payload["script"] = script_block

    plots = build_plots_for_script(store, script_id)
    payload["plots"] = plots

    assets = list(payload.get("assets") or [])
    assets_with_images = build_assets_with_images_from_scan(assets)
    payload["linked_image_count"] = len(assets_with_images)
    payload["assets_with_images"] = assets_with_images
    payload["plot_count"] = len(plots)

    payload["characters"] = [a for a in assets if a.get("type") == TextAssetType.CHARACTER.value]
    payload["scenes"] = [a for a in assets if a.get("type") == TextAssetType.SCENE.value]
    payload["props"] = [a for a in assets if a.get("type") == TextAssetType.PROP.value]
    payload["voice_roles"] = _voice_summary_from_assets(assets)
    payload["narration_assets"] = [
        a for a in assets if a.get("type") == TextAssetType.NARRATION.value
    ]
    from core.llm.tools.tts.settings import TtsSettings

    default_narrator_voice = TtsSettings().default_voice
    payload["voice_speakers"] = build_available_voice_speakers(
        store,
        script_id,
        default_narrator_voice=default_narrator_voice,
    )
    payload["voice_content_note"] = (
        "镜内配音幕须写入 create_shots 的 audio_tracks[kind=voice].clips[]；"
        "每条 clip 须明确说话人：角色对白填 character_ref=voice_speakers 中角色的 txt_*，"
        "旁白/画外音 character_ref 留空；不同说话人须拆成多条 clip，禁止混写于单条 text。"
        "narration_assets 仅供参考，TTS 不会从剧本旁白资产自动回填。"
    )
    return payload
