"""用户上传镜内配音音频：落盘、探测时长、生成句级字幕 cue 并绑定 voice clip。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.edit.shot_detail_sync import bind_voice_clip_media
from core.edit.subtitle_align import build_cues_for_audio_media
from core.llm.agent.llm_action import _persist_media
from core.llm.tools.shared.media_list import build_media_item
from core.models.entities import MediaAssetType, new_id
from core.store.memory import MemoryStore
from core.store.project_paths import script_media_dir
from core.tts.duration import duration_ms_from_target

_ALLOWED_SUFFIX = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".aac", ".flac"}


def _safe_suffix(filename: str) -> str:
    """从文件名解析允许的后缀，默认 mp3。"""
    suffix = Path(filename or "voice.mp3").suffix.lower()
    return suffix if suffix in _ALLOWED_SUFFIX else ".mp3"


def ingest_voice_audio_upload(
    store: MemoryStore,
    *,
    project_id: str,
    script_id: str,
    shot_id: str,
    file_bytes: bytes,
    filename: str,
    narration_text: str = "",
    clip_id: str | None = None,
    bind_clip: bool = True,
) -> dict[str, Any]:
    """保存上传音频为 MediaAsset，生成 subtitle_cues，可选绑定到镜内 voice clip 并同步字幕。"""
    if not file_bytes:
        raise ValueError("音频文件为空")
    script = store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise ValueError("剧本不存在")
    plan = store.get_video_plan_for_script(script_id)
    if not plan:
        raise ValueError("未找到视频计划稿")
    shot = next((s for s in plan.shots if s.id == shot_id), None)
    if not shot:
        raise ValueError("镜头不存在")

    media_id = new_id("media")
    suffix = _safe_suffix(filename)
    media_dir = script_media_dir(project_id, script_id)
    media_dir.mkdir(parents=True, exist_ok=True)
    output_path = media_dir / f"{media_id}{suffix}"
    output_path.write_bytes(file_bytes)

    duration_ms = duration_ms_from_target(output_path)
    if duration_ms <= 0:
        output_path.unlink(missing_ok=True)
        raise ValueError("无法读取音频时长，请检查文件格式或 FFmpeg 是否可用")

    text = (narration_text or "").strip()
    temp_meta: dict[str, Any] = {
        "shot_id": shot_id,
        "duration_ms": duration_ms,
        "narration_text": text[:500],
        "source": "upload",
    }
    if clip_id:
        temp_meta["voice_clip_id"] = clip_id

    temp_media = type(
        "TempMedia",
        (),
        {"metadata": temp_meta, "id": media_id},
    )()
    subtitle_cues = build_cues_for_audio_media(store, temp_media, narration_text=text)
    if subtitle_cues:
        temp_meta["subtitle_cues"] = subtitle_cues

    label = Path(filename or "voice").stem[:80] or f"shot_{shot.order}_voice"
    media = _persist_media(
        store,
        project_id=project_id,
        script_id=script_id,
        media_type=MediaAssetType.AUDIO,
        name=label,
        url=str(output_path.resolve()),
        asset_id=media_id,
        metadata=temp_meta,
    )

    sync_result: dict[str, Any] | None = None
    if bind_clip:
        sync_result = bind_voice_clip_media(
            store,
            script_id,
            shot_id,
            media.id,
            clip_id=clip_id,
        )

    item = build_media_item(store, media)
    return {
        "media_id": media.id,
        "duration_ms": duration_ms,
        "subtitle_cues": subtitle_cues,
        "link": item.get("link") or item.get("url"),
        "sync": sync_result,
    }
