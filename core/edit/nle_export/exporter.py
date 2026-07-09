"""Premiere Pro 工程包导出主入口。"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from core.edit.asset_resolver import validate_edit_timeline
from core.edit.export_settings import ExportConfigManager, ExportSettings, get_export_manager
from core.edit.nle_export.errors import NleExportError
from core.edit.nle_export.media_bundle import stage_media_files
from core.edit.nle_export.packager import create_zip
from core.edit.nle_export.srt_writer import write_srt
from core.edit.nle_export.xmeml_writer import write_xmeml
from core.edit.subtitle_align import enrich_subtitles_from_audio
from core.edit.timeline import (
    enrich_timeline_audio_from_store,
    ensure_video_layers,
    normalize_timeline_motions,
)
from core.models.entities import EditTimeline
from core.store.memory import MemoryStore


@dataclass
class NleExportResult:
    """NLE 工程包导出结果。"""

    output_path: Path
    duration_ms: int
    media_count: int
    clip_count: int
    format: str = "fcp7_xmeml"


def _validation_error_message(validation) -> str:
    """将校验报告转为可读错误信息。"""
    items = validation.missing_items or []
    if not items:
        return "剪辑素材未齐备"
    reasons = [m.reason for m in items[:5] if m.reason]
    return "；".join(reasons) if reasons else "剪辑素材未齐备"


def export_timeline_to_premiere_package(
    store: MemoryStore,
    timeline: EditTimeline,
    output_path: Path,
    *,
    project_id: str,
    script_id: str,
    sequence_name: str = "",
    manager: ExportConfigManager | None = None,
    skip_subtitles: bool = False,
) -> NleExportResult:
    """将 EditTimeline 导出为 Premiere 可导入的 FCP7 XMEML ZIP 工程包。"""
    settings_mgr = manager or get_export_manager()
    settings: ExportSettings = settings_mgr.get_settings()

    timeline = ensure_video_layers(timeline)
    plan = store.get_video_plan_for_script(script_id)
    timeline = enrich_timeline_audio_from_store(store, timeline, plan)
    if not skip_subtitles:
        timeline = enrich_subtitles_from_audio(store, timeline, plan)
    timeline = normalize_timeline_motions(timeline)

    validation = validate_edit_timeline(store, timeline)
    if not validation.ready:
        raise NleExportError(_validation_error_message(validation))

    script = store.get_script(script_id)
    seq_name = sequence_name or (script.title if script else "") or script_id

    temp_dir = Path(tempfile.mkdtemp(prefix="svg-nle-"))
    try:
        bundle = stage_media_files(
            store,
            timeline,
            project_id=project_id,
            script_id=script_id,
            staging_dir=temp_dir,
        )
        project_xml = write_xmeml(
            store,
            timeline,
            bundle,
            sequence_name=seq_name,
            fps=settings.fps,
            width=settings.width,
            height=settings.height,
        )
        srt_content = write_srt(timeline)
        create_zip(
            staging_dir=temp_dir,
            output_path=output_path,
            project_xml=project_xml,
            srt_content=srt_content,
            sequence_name=seq_name,
        )
        clip_count = sum(len(layer.clips) for layer in timeline.video_layers)
        clip_count += len(timeline.tracks.get("audio", []))
        from core.edit.timeline import timeline_duration_ms

        return NleExportResult(
            output_path=output_path,
            duration_ms=timeline_duration_ms(timeline),
            media_count=len(bundle.path_by_media_id),
            clip_count=clip_count,
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
