"""配音幕说话人：角色对白与旁白的解析、可选列表与校验。"""

from __future__ import annotations

from core.assets.service import apply_character_tts_voice
from core.models.entities import Shot, ShotAudioClip, TextAssetType
from core.models.image_text_asset import CharacterContent, normalize_image_text_content
from core.store.memory import MemoryStore

NARRATOR_SPEAKER_KIND = "narrator"
CHARACTER_SPEAKER_KIND = "character"


def voice_clip_speaker_kind(clip: ShotAudioClip) -> str:
    """推断 clip 说话人类型：有 character_ref 为角色对白，否则为旁白。"""
    if str(clip.character_ref or "").strip():
        return CHARACTER_SPEAKER_KIND
    return NARRATOR_SPEAKER_KIND


def is_narrator_voice_clip(clip: ShotAudioClip) -> bool:
    """判断 clip 是否按旁白/画外音处理。"""
    return voice_clip_speaker_kind(clip) == NARRATOR_SPEAKER_KIND


def _character_ids_for_script(store: MemoryStore, script_id: str) -> dict[str, str]:
    """返回剧本内可用角色 {asset_id: name}。"""
    out: dict[str, str] = {}
    for asset in store.list_assets_for_script(script_id):
        if asset.type != TextAssetType.CHARACTER:
            continue
        out[asset.id] = str(asset.name or asset.id)
    return out


def build_available_voice_speakers(
    store: MemoryStore,
    script_id: str,
    *,
    default_narrator_voice: str = "",
) -> list[dict[str, str]]:
    """列出配音幕可选说话人：旁白 + 已生成角色（供 load_context 与前端对齐）。"""
    speakers: list[dict[str, str]] = [
        {
            "kind": NARRATOR_SPEAKER_KIND,
            "character_ref": "",
            "name": "旁白",
            "tts_voice": str(default_narrator_voice or "").strip(),
            "usage": "画外叙述、场景说明、无明确说话人的文案；character_ref 留空",
        }
    ]
    for asset in store.list_assets_for_script(script_id):
        if asset.type != TextAssetType.CHARACTER:
            continue
        voice = ""
        try:
            content = CharacterContent.model_validate(
                normalize_image_text_content(TextAssetType.CHARACTER, dict(asset.content or {}))
            )
            normalized = apply_character_tts_voice(content.model_dump())
            voice = str(normalized.get("tts_voice") or "").strip()
        except Exception:
            pass
        speakers.append(
            {
                "kind": CHARACTER_SPEAKER_KIND,
                "character_ref": asset.id,
                "name": str(asset.name or asset.id),
                "tts_voice": voice,
                "usage": "该角色在镜内的对白；character_ref 必填为对应 txt_*",
            }
        )
    return speakers


def validate_shot_voice_speakers(
    shot: Shot,
    store: MemoryStore,
    script_id: str,
) -> list[str]:
    """校验镜内 voice clip 的 character_ref 须为空（旁白）或指向已生成角色。"""
    issues: list[str] = []
    label = shot.id or f"镜{shot.order + 1}"
    char_ids = _character_ids_for_script(store, script_id)
    for track in shot.audio_tracks:
        if track.kind != "voice":
            continue
        for idx, clip in enumerate(track.clips):
            text = str(clip.text or "").strip()
            if not text:
                continue
            ref = str(clip.character_ref or "").strip()
            if not ref:
                continue
            if ref not in char_ids:
                clip_label = clip.id or f"第{idx + 1}条"
                issues.append(
                    f"{label}: 配音幕 {clip_label} 的 character_ref={ref} "
                    f"不是 load_context.characters 中的已生成角色"
                )
    return issues


def validate_shots_voice_speakers(
    shots: list[Shot],
    store: MemoryStore,
    script_id: str,
) -> dict[str, list[str]]:
    """批量校验配音说话人，返回 {shot_id: [问题...]}。"""
    result: dict[str, list[str]] = {}
    for shot in shots:
        issues = validate_shot_voice_speakers(shot, store, script_id)
        if issues:
            result[shot.id] = issues
    return result
