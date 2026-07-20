"""NLE 导出素材打包：复制媒体到 staging 目录并建立相对路径映射。"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from core.edit.asset_resolver import resolve_clip_media, shot_by_id_for_script
from core.edit.media_paths import ExportMediaError, resolve_local_path_for_url
from core.edit.nle_export.errors import NleExportError
from core.edit.timeline import timeline_duration_ms
from core.models.entities import EditClip, EditTimeline, MediaAssetType
from core.store.memory import MemoryStore


@dataclass
class MediaBundle:
    """已暂存的素材包：media_id → ZIP 内相对路径。"""

    staging_dir: Path
    path_by_media_id: dict[str, str] = field(default_factory=dict)
    clip_media_id: dict[str, str] = field(default_factory=dict)


def _safe_filename(media_id: str, suffix: str) -> str:
    """生成 ZIP 内安全的素材文件名。"""
    clean_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in media_id)
    return f"{safe_id}{clean_suffix}"


def _resolve_clip_bundle_path(
    store: MemoryStore,
    clip: EditClip,
    *,
    project_id: str,
    script_id: str,
    shot_by_id,
    media_dir: Path,
    path_by_media_id: dict[str, str],
) -> str | None:
    """解析 clip 媒体并复制到 staging/media，返回相对路径。"""
    resolved = resolve_clip_media(
        store,
        clip,
        script_id=script_id,
        shot_by_id=shot_by_id,
    )
    if resolved is None:
        return None

    media_id = resolved.media_id
    if media_id in path_by_media_id:
        return path_by_media_id[media_id]

    media = store.media_assets.get(media_id)
    if media is None:
        raise NleExportError(f"素材 {media_id} 不存在")

    try:
        local = resolve_local_path_for_url(
            store,
            project_id=project_id,
            script_id=script_id,
            media_id=media_id,
            url=media.url or "",
            media_type=media.type.value if hasattr(media.type, "value") else str(media.type),
        )
    except ExportMediaError as exc:
        raise NleExportError(str(exc)) from exc

    suffix = local.suffix.lower() or ".bin"
    dest_name = _safe_filename(media_id, suffix)
    dest = media_dir / dest_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(local, dest)

    rel = f"media/{dest_name}"
    path_by_media_id[media_id] = rel
    return rel


def stage_media_files(
    store: MemoryStore,
    timeline: EditTimeline,
    *,
    project_id: str,
    script_id: str,
    staging_dir: Path,
) -> MediaBundle:
    """复制时间轴引用的全部媒体到 staging/media 目录。"""
    shot_by_id = shot_by_id_for_script(store, script_id)
    media_dir = staging_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    path_by_media_id: dict[str, str] = {}
    clip_media_id: dict[str, str] = {}

    for layer in sorted(timeline.video_layers, key=lambda item: item.z_index):
        for clip in layer.clips:
            rel = _resolve_clip_bundle_path(
                store,
                clip.model_copy(update={"track": "video"}),
                project_id=project_id,
                script_id=script_id,
                shot_by_id=shot_by_id,
                media_dir=media_dir,
                path_by_media_id=path_by_media_id,
            )
            if rel:
                resolved = resolve_clip_media(
                    store,
                    clip.model_copy(update={"track": "video"}),
                    script_id=script_id,
                    shot_by_id=shot_by_id,
                )
                if resolved:
                    clip_media_id[clip.id] = resolved.media_id

    for clip in timeline.tracks.get("audio", []):
        rel = _resolve_clip_bundle_path(
            store,
            clip,
            project_id=project_id,
            script_id=script_id,
            shot_by_id=shot_by_id,
            media_dir=media_dir,
            path_by_media_id=path_by_media_id,
        )
        if rel:
            resolved = resolve_clip_media(
                store,
                clip,
                script_id=script_id,
                shot_by_id=shot_by_id,
            )
            if resolved:
                clip_media_id[clip.id] = resolved.media_id

    if not path_by_media_id:
        raise NleExportError("时间轴无可用媒体素材")

    return MediaBundle(
        staging_dir=staging_dir,
        path_by_media_id=path_by_media_id,
        clip_media_id=clip_media_id,
    )


def media_kind_for_id(store: MemoryStore, media_id: str) -> str:
    """返回素材类型：image / video / audio。"""
    media = store.media_assets.get(media_id)
    if media is None:
        return "video"
    if media.type == MediaAssetType.AUDIO:
        return "audio"
    if media.type == MediaAssetType.VIDEO:
        return "video"
    return "image"
