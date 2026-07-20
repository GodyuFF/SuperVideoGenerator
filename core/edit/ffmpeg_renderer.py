"""EditTimeline → MP4（FFmpeg 导出，替代 Remotion 默认路径）。"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.edit.asset_resolver import resolve_clip_media, validate_edit_timeline
from core.edit.subtitle_burn import burn_subtitles, write_ass_file
from core.edit.compose import compose_timeline_plan
from core.edit.compose import _shot_by_id_for_timeline
from core.edit.export_settings import ExportConfigManager, ExportSettings, get_export_manager
from core.tts.ffmpeg_util import ffmpeg_missing_message, is_ffmpeg_available
from core.edit.media_paths import ExportMediaError, resolve_local_path_for_url
from core.edit.subtitle_align import enrich_subtitles_from_audio
from core.edit.timeline import (
    enrich_timeline_audio_from_store,
    flat_video_clips,
    normalize_timeline_motions,
    timeline_duration_ms,
    validate_timeline_clips,
    build_timeline_layer_summary,
)
from core.edit.transform_interp import (
    ResolvedTransform,
    build_scaled_video_filter,
    snap_even_dim,
    timeline_needs_composite_export,
    transform_to_overlay_pixels,
)
from core.execution.cancel import check_cancelled
from core.models.entities import EditTimeline, MediaAssetType, VideoStyleMode
from core.store.memory import MemoryStore

logger = logging.getLogger("core.edit.ffmpeg_renderer")


class FfmpegExportError(RuntimeError):
    """FFmpeg 导出失败。"""


@dataclass
class FfmpegExportResult:
    output_path: Path
    duration_ms: int
    segment_count: int


def _extract_ffmpeg_error(stderr: str, *, max_len: int = 2000) -> str:
    """从 FFmpeg stderr 提取有效错误（跳过 version 头，保留尾部）。"""
    text = (stderr or "").strip()
    if not text:
        return "未知错误（无 stderr）"
    lines = text.splitlines()
    keywords = ("error", "invalid", "failed", "no such", "cannot", "unable", "not found")
    important = [
        line.strip()
        for line in lines
        if any(keyword in line.lower() for keyword in keywords)
    ]
    if important:
        body = "\n".join(important[-20:])
    else:
        body_lines: list[str] = []
        skip_header = True
        for line in lines:
            lower = line.lower()
            if skip_header and (
                "ffmpeg version" in lower
                or "configuration:" in lower
                or line.strip() == ""
                or line.startswith("  ")
            ):
                continue
            skip_header = False
            body_lines.append(line)
        body = "\n".join(body_lines) if body_lines else text
    if len(body) > max_len:
        return body[-max_len:]
    return body


def _run_ffmpeg(
    cmd: list[str],
    *,
    label: str,
    clip_id: str = "",
    layer_name: str = "",
) -> None:
    logger.debug("ffmpeg %s: %s", label, " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        err = _extract_ffmpeg_error(proc.stderr or proc.stdout or "")
        ctx = label
        if clip_id:
            ctx += f" clip={clip_id}"
        if layer_name:
            ctx += f" layer={layer_name}"
        raise FfmpegExportError(f"{ctx} 失败：{err}")


def _scale_pad_filter(width: int, height: int) -> str:
    w = snap_even_dim(width)
    h = snap_even_dim(height)
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"
    )


def _render_image_segment(
    *,
    ffmpeg: str,
    image_path: Path,
    duration_sec: float,
    output_path: Path,
    settings: ExportSettings,
    transform: dict[str, Any] | None = None,
) -> None:
    if _transform_needs_overlay(transform):
        _render_clip_with_transform(
            ffmpeg=ffmpeg,
            local=image_path,
            media_type=MediaAssetType.IMAGE,
            duration_sec=duration_sec,
            output_path=output_path,
            settings=settings,
            transform=transform or {},
        )
        return
    vf = _scale_pad_filter(settings.width, settings.height)
    cmd = [
        ffmpeg,
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-t",
        f"{max(duration_sec, 0.1):.3f}",
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(settings.fps),
        "-crf",
        str(settings.crf),
        str(output_path),
    ]
    _run_ffmpeg(cmd, label="图片片段")


def _render_video_segment(
    *,
    ffmpeg: str,
    video_path: Path,
    duration_sec: float,
    output_path: Path,
    settings: ExportSettings,
    transform: dict[str, Any] | None = None,
    playback_rate: float = 1.0,
    freeze_tail_ms: int = 0,
) -> None:
    """渲染真视频片段；支持 playback_rate 慢放与尾帧 freeze 垫时长。"""
    if _transform_needs_overlay(transform):
        _render_clip_with_transform(
            ffmpeg=ffmpeg,
            local=video_path,
            media_type=MediaAssetType.VIDEO,
            duration_sec=duration_sec,
            output_path=output_path,
            settings=settings,
            transform=transform or {},
        )
        return

    rate = float(playback_rate or 1.0)
    if rate <= 0:
        rate = 1.0
    freeze_sec = max(0.0, int(freeze_tail_ms or 0) / 1000.0)
    target_sec = max(duration_sec, 0.1)

    vf_parts = [_scale_pad_filter(settings.width, settings.height)]
    # NLE 语义：rate<1 慢放 → setpts 放大 PTS；rate>1 加速 → 缩小 PTS
    if abs(rate - 1.0) > 0.001:
        vf_parts.append(f"setpts={1.0 / rate:.6f}*PTS")
    if freeze_sec > 0.05:
        vf_parts.append(f"tpad=stop_mode=clone:stop_duration={freeze_sec:.3f}")
    vf = ",".join(vf_parts)

    # 输入侧：若只要 rate/freeze，仍用 -t 限制输出总长
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-t",
        f"{target_sec:.3f}",
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(settings.fps),
        "-crf",
        str(settings.crf),
        "-an",
        str(output_path),
    ]
    _run_ffmpeg(cmd, label="视频片段")


def _clip_playback_rate(clip: Any) -> float:
    """从 EditClip.metadata 读取 playback_rate。"""
    meta = getattr(clip, "metadata", None) or {}
    try:
        return float(meta.get("playback_rate") or 1.0)
    except (TypeError, ValueError):
        return 1.0


def _clip_freeze_tail_ms(clip: Any) -> int:
    """从 EditClip.metadata 读取 freeze_tail_ms。"""
    meta = getattr(clip, "metadata", None) or {}
    try:
        return max(0, int(meta.get("freeze_tail_ms") or 0))
    except (TypeError, ValueError):
        return 0


def _concat_segments(ffmpeg: str, segment_files: list[Path], output_path: Path) -> None:
    list_file = output_path.parent / "concat_list.txt"
    lines = [f"file '{p.resolve().as_posix()}'" for p in segment_files]
    list_file.write_text("\n".join(lines), encoding="utf-8")
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
        str(output_path),
    ]
    _run_ffmpeg(cmd, label="拼接视频轨")


def _atempo_filter(rate: float) -> str:
    """生成 atempo 滤镜链（单段 0.5–2.0）。"""
    r = float(rate or 1.0)
    if r <= 0:
        r = 1.0
    r = max(0.5, min(2.0, r))
    if abs(r - 1.0) < 0.001:
        return ""
    return f"atempo={r:.4f}"


def _mix_audio_tracks(
    ffmpeg: str,
    audio_inputs: list[tuple[Path, int, float]],
    duration_sec: float,
    output_path: Path,
) -> None:
    """混音；每项为 (path, delay_ms, playback_rate)。"""
    if not audio_inputs:
        return
    if len(audio_inputs) == 1:
        path, delay_ms, rate = audio_inputs[0]
        af_parts = [f"adelay={delay_ms}|{delay_ms}"]
        atempo = _atempo_filter(rate)
        if atempo:
            af_parts.append(atempo)
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(path),
            "-af",
            ",".join(af_parts),
            "-t",
            f"{max(duration_sec, 0.1):.3f}",
            "-c:a",
            "aac",
            str(output_path),
        ]
        _run_ffmpeg(cmd, label="单轨配音")
        return

    inputs: list[str] = []
    filters: list[str] = []
    for idx, (path, delay_ms, rate) in enumerate(audio_inputs):
        inputs.extend(["-i", str(path)])
        parts = [f"adelay={delay_ms}|{delay_ms}"]
        atempo = _atempo_filter(rate)
        if atempo:
            parts.append(atempo)
        filters.append(f"[{idx}:a]{','.join(parts)}[a{idx}]")
    mix_inputs = "".join(f"[a{i}]" for i in range(len(audio_inputs)))
    filter_complex = ";".join(filters) + f";{mix_inputs}amix=inputs={len(audio_inputs)}:duration=longest[aout]"
    cmd = [
        ffmpeg,
        "-y",
        *inputs,
        "-filter_complex",
        filter_complex,
        "-map",
        "[aout]",
        "-t",
        f"{max(duration_sec, 0.1):.3f}",
        "-c:a",
        "aac",
        str(output_path),
    ]
    _run_ffmpeg(cmd, label="混音")


def _mux_av(ffmpeg: str, video_path: Path, audio_path: Path | None, output_path: Path) -> None:
    if audio_path and audio_path.is_file():
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(output_path),
        ]
    else:
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-c:v",
            "copy",
            "-an",
            str(output_path),
        ]
    _run_ffmpeg(cmd, label="封装成片")


def _resolve_media_path(
    store: MemoryStore,
    *,
    project_id: str,
    script_id: str,
    media_id: str,
    media_type: str,
    url: str,
) -> Path:
    try:
        return resolve_local_path_for_url(
            store,
            project_id=project_id,
            script_id=script_id,
            media_id=media_id,
            url=url,
            media_type=media_type,
        )
    except ExportMediaError as exc:
        raise FfmpegExportError(str(exc)) from exc


def _find_video_clip(timeline: EditTimeline, clip_id: str):
    for layer in timeline.video_layers:
        for clip in layer.clips:
            if clip.id == clip_id:
                return clip, layer
    return None, None


def _transform_from_dict(raw: dict[str, Any]) -> ResolvedTransform:
    return ResolvedTransform(
        x=float(raw.get("x", 0.5)),
        y=float(raw.get("y", 0.5)),
        width=float(raw.get("width", 1.0)),
        height=float(raw.get("height", 1.0)),
        opacity=float(raw.get("opacity", 1.0)),
        rotation=float(raw.get("rotation", 0.0)),
        scale=float(raw.get("scale", 1.0)),
    )


def _transform_needs_overlay(transform: dict[str, Any] | None) -> bool:
    if not transform:
        return False
    resolved = _transform_from_dict(transform)
    if abs(resolved.scale - 1.0) > 1e-3:
        return True
    defaults = ResolvedTransform(
        x=0.5, y=0.5, width=1.0, height=1.0, opacity=1.0, rotation=0.0, scale=1.0
    )
    for attr in ("x", "y", "width", "height", "opacity", "rotation"):
        if abs(getattr(resolved, attr) - getattr(defaults, attr)) > 1e-3:
            return True
    return False


def _render_clip_with_transform(
    *,
    ffmpeg: str,
    local: Path,
    media_type: MediaAssetType,
    duration_sec: float,
    output_path: Path,
    settings: ExportSettings,
    transform: dict[str, Any],
) -> None:
    """单层 clip：transform 缩放/位移后叠到画布（与 composite 单层分支一致）。"""
    layer_path = output_path.parent / f"{output_path.stem}_layer.mp4"
    _render_layer_source(
        ffmpeg=ffmpeg,
        local=local,
        media_type=media_type,
        duration_sec=duration_sec,
        output_path=layer_path,
        settings=settings,
        transform=transform,
    )
    pixels = transform_to_overlay_pixels(
        _transform_from_dict(transform),
        canvas_width=settings.width,
        canvas_height=settings.height,
    )
    x, y = pixels["x"], pixels["y"]
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s={settings.width}x{settings.height}:d={duration_sec:.3f}",
        "-i",
        str(layer_path),
        "-filter_complex",
        f"[1:v]format=yuva420p[fg];[0:v][fg]overlay={x}:{y}:shortest=1",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(settings.fps),
        str(output_path),
    ]
    _run_ffmpeg(cmd, label="transform 片段")
    layer_path.unlink(missing_ok=True)


def _render_layer_source(
    *,
    ffmpeg: str,
    local: Path,
    media_type: MediaAssetType,
    duration_sec: float,
    output_path: Path,
    settings: ExportSettings,
    transform: dict[str, Any],
    clip_id: str = "",
    layer_name: str = "",
) -> None:
    tr = transform or {}
    resolved = _transform_from_dict(transform or {})
    vf = build_scaled_video_filter(
        resolved,
        canvas_width=settings.width,
        canvas_height=settings.height,
    )
    if media_type == MediaAssetType.VIDEO:
        cmd = [
            ffmpeg, "-y", "-i", str(local),
            "-t", f"{max(duration_sec, 0.1):.3f}",
            "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-r", str(settings.fps), "-crf", str(settings.crf), "-an", str(output_path),
        ]
    else:
        cmd = [
            ffmpeg, "-y", "-loop", "1", "-i", str(local),
            "-t", f"{max(duration_sec, 0.1):.3f}",
            "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-r", str(settings.fps), "-crf", str(settings.crf), str(output_path),
        ]
    _run_ffmpeg(
        cmd,
        label="图层素材",
        clip_id=clip_id,
        layer_name=layer_name,
    )


def _render_composite_slice(
    *,
    ffmpeg: str,
    slice_data: dict[str, Any],
    store: MemoryStore,
    timeline: EditTimeline,
    project_id: str,
    script_id: str,
    settings: ExportSettings,
    temp_dir: Path,
    idx: int,
    shot_by_id: dict,
) -> Path:
    duration_sec = max(
        (int(slice_data.get("end_ms", 0)) - int(slice_data.get("start_ms", 0))) / 1000.0,
        0.1,
    )
    layers = slice_data.get("layers") or []
    out_path = temp_dir / f"slice_{idx:03d}.mp4"
    if not layers:
        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", f"color=c=black:s={settings.width}x{settings.height}:d={duration_sec:.3f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(settings.fps),
            str(out_path),
        ]
        _run_ffmpeg(cmd, label="空片段")
        return out_path

    layer_paths: list[tuple[Path, dict[str, int]]] = []
    for layer_idx, layer_info in enumerate(layers):
        clip_id = str(layer_info.get("clip_id", ""))
        clip, layer = _find_video_clip(timeline, clip_id)
        if clip is None:
            continue
        resolved = resolve_clip_media(store, clip, script_id=script_id, shot_by_id=shot_by_id)
        if not resolved:
            continue
        media = store.media_assets.get(resolved.media_id)
        if not media:
            continue
        local = _resolve_media_path(
            store,
            project_id=project_id,
            script_id=script_id,
            media_id=media.id,
            media_type=media.type.value,
            url=media.url,
        )
        layer_path = temp_dir / f"slice_{idx}_layer_{layer_idx}.mp4"
        _render_layer_source(
            ffmpeg=ffmpeg,
            local=local,
            media_type=media.type,
            duration_sec=duration_sec,
            output_path=layer_path,
            settings=settings,
            transform=layer_info.get("transform") or {},
            clip_id=clip_id,
            layer_name=(layer.name if layer else "") or (layer.id if layer else ""),
        )
        pixels = transform_to_overlay_pixels(
            _transform_from_dict(layer_info.get("transform") or {}),
            canvas_width=settings.width,
            canvas_height=settings.height,
        )
        layer_paths.append((layer_path, pixels))

    if not layer_paths:
        clip_ids = [
            str(layer_info.get("clip_id", ""))
            for layer_info in layers
            if layer_info.get("clip_id")
        ]
        detail = "、".join(clip_ids) if clip_ids else "未知片段"
        raise FfmpegExportError(
            f"合成片段无法解析图片素材（{detail}）。"
            "请先完成 image_gen 生图，或在剪辑工作室为片段绑定可访问的媒体。"
        )

    if len(layer_paths) == 1:
        path, pixels = layer_paths[0]
        x, y = pixels["x"], pixels["y"]
        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", f"color=c=black:s={settings.width}x{settings.height}:d={duration_sec:.3f}",
            "-i", str(path),
            "-filter_complex", f"[1:v]format=yuva420p[fg];[0:v][fg]overlay={x}:{y}:shortest=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(settings.fps),
            str(out_path),
        ]
        _run_ffmpeg(cmd, label="单层合成")
        return out_path

    inputs = ["-f", "lavfi", "-i", f"color=c=black:s={settings.width}x{settings.height}:d={duration_sec:.3f}"]
    for path, _ in layer_paths:
        inputs.extend(["-i", str(path)])
    chain = "[0:v]"
    for i, (_, pixels) in enumerate(layer_paths):
        x, y = pixels["x"], pixels["y"]
        nxt = f"[v{i}]" if i < len(layer_paths) - 1 else "[vout]"
        chain += f"[{i + 1}:v]overlay={x}:{y}{nxt};"
        if i < len(layer_paths) - 1:
            chain = chain.replace(f"[v{i}];", f"[v{i}]")
    filter_complex = chain.rstrip(";")
    # rebuild filter properly
    filters: list[str] = []
    base = "[0:v]"
    for i, (_, pixels) in enumerate(layer_paths):
        x, y = pixels["x"], pixels["y"]
        out_label = f"[v{i}]" if i < len(layer_paths) - 1 else "[vout]"
        filters.append(f"{base}[{i + 1}:v]overlay={x}:{y}{out_label}")
        base = out_label
    filter_complex = ";".join(filters)
    cmd = [
        ffmpeg, "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(settings.fps),
        str(out_path),
    ]
    _run_ffmpeg(cmd, label="多层合成")
    return out_path


def _validation_error_message(report) -> str:
    reasons = [m.reason for m in report.missing_items if m.reason]
    if not reasons:
        return "剪辑时间轴素材未齐备，无法导出成片"
    preview = "；".join(reasons[:3])
    if len(reasons) > 3:
        preview += f" 等共 {len(reasons)} 项"
    upstream = next(
        (m.suggested_upstream for m in report.missing_items if m.suggested_upstream != "none"),
        None,
    )
    hint = ""
    if upstream == "image_gen":
        hint = "。建议先运行 image_gen 生成配图"
    elif upstream == "tts_gen":
        hint = "。建议先运行 tts_gen 生成配音"
    elif upstream == "storyboard":
        hint = "。建议先运行 storyboard / plan_edit_timeline"
    return f"{preview}{hint}"


def export_timeline_to_mp4(
    store: MemoryStore,
    timeline: EditTimeline,
    output_path: Path,
    *,
    project_id: str,
    script_id: str,
    style_mode: VideoStyleMode = VideoStyleMode.STORYBOOK,
    manager: ExportConfigManager | None = None,
    skip_subtitles: bool = False,
) -> FfmpegExportResult:
    """将 EditTimeline 导出为 MP4。"""
    check_cancelled(script_id)
    settings_mgr = manager or get_export_manager()
    settings = settings_mgr.get_settings()
    if not settings_mgr.is_ffmpeg_export_enabled():
        from core.edit.export_settings import CLASSIC_EXPORT_ONLY_MESSAGE

        raise FfmpegExportError(CLASSIC_EXPORT_ONLY_MESSAGE)

    ffmpeg = settings_mgr.resolve_ffmpeg()
    if not is_ffmpeg_available(ffmpeg):
        raise FfmpegExportError(ffmpeg_missing_message(ffmpeg))

    plan = store.get_video_plan_for_script(script_id)
    timeline = enrich_timeline_audio_from_store(store, timeline, plan)
    if not skip_subtitles:
        timeline = enrich_subtitles_from_audio(store, timeline, plan)
    timeline = normalize_timeline_motions(timeline)
    validation = validate_edit_timeline(store, timeline)
    if not validation.ready:
        raise FfmpegExportError(_validation_error_message(validation))

    clip_warnings = validate_timeline_clips(timeline)
    video_overlap = [
        w for w in clip_warnings if "视频层" in w and "与同层片段重叠" in w
    ]
    if video_overlap:
        layer_summary = build_timeline_layer_summary(store, timeline)
        detail = json.dumps(
            {
                "same_layer_overlaps": layer_summary.get("same_layer_overlaps") or [],
                "warnings": video_overlap,
            },
            ensure_ascii=False,
            indent=2,
        )
        raise FfmpegExportError(
            "时间轴同层 clip 重叠，无法合成。请拆分 video_layers 或调整片段时间。\n"
            f"{detail}"
        )

    compose_plan = compose_timeline_plan(store, timeline, style_mode=style_mode)
    segments = compose_plan.get("segments") or []
    composite_slices = compose_plan.get("composite_slices") or []
    if not segments and not composite_slices:
        raise FfmpegExportError("时间轴无视频片段可导出")

    duration_ms = timeline_duration_ms(timeline)
    duration_sec = max(duration_ms / 1000.0, 0.1)
    shot_by_id = _shot_by_id_for_timeline(store, timeline)

    use_composite = (
        style_mode != VideoStyleMode.AI_VIDEO and bool(composite_slices)
    ) or timeline_needs_composite_export(timeline) or any(
        len(s.get("layers", [])) > 1 for s in composite_slices
    )

    temp_dir = Path(tempfile.mkdtemp(prefix="svg-ffmpeg-"))
    segment_files: list[Path] = []

    try:
        if use_composite and composite_slices:
            for idx, slc in enumerate(composite_slices):
                check_cancelled(script_id)
                segment_files.append(
                    _render_composite_slice(
                        ffmpeg=ffmpeg,
                        slice_data=slc,
                        store=store,
                        timeline=timeline,
                        project_id=project_id,
                        script_id=script_id,
                        settings=settings,
                        temp_dir=temp_dir,
                        idx=idx,
                        shot_by_id=shot_by_id,
                    )
                )
        else:
            for idx, seg in enumerate(segments):
                check_cancelled(script_id)
                clip_id = str(seg.get("clip_id", f"seg{idx}"))
                clip, _ = _find_video_clip(timeline, clip_id)
                if clip is None:
                    continue
                resolved = resolve_clip_media(
                    store, clip, script_id=script_id, shot_by_id=shot_by_id
                )
                if not resolved:
                    raise FfmpegExportError(f"片段 {clip_id} 无法解析素材")
                media = store.media_assets.get(resolved.media_id)
                if not media:
                    raise FfmpegExportError(f"媒体 {resolved.media_id} 不存在")

                local = _resolve_media_path(
                    store,
                    project_id=project_id,
                    script_id=script_id,
                    media_id=media.id,
                    media_type=media.type.value,
                    url=media.url,
                )
                seg_path = temp_dir / f"seg_{idx:03d}.mp4"
                seg_duration = max((clip.end_ms - clip.start_ms) / 1000.0, 0.1)
                transform = seg.get("transform") or {}
                if media.type == MediaAssetType.VIDEO:
                    _render_video_segment(
                        ffmpeg=ffmpeg,
                        video_path=local,
                        duration_sec=seg_duration,
                        output_path=seg_path,
                        settings=settings,
                        transform=transform,
                        playback_rate=_clip_playback_rate(clip),
                        freeze_tail_ms=_clip_freeze_tail_ms(clip),
                    )
                else:
                    _render_image_segment(
                        ffmpeg=ffmpeg,
                        image_path=local,
                        duration_sec=seg_duration,
                        output_path=seg_path,
                        settings=settings,
                        transform=transform,
                    )
                segment_files.append(seg_path)

        if not segment_files:
            raise FfmpegExportError("未生成任何视频片段")

        video_only = temp_dir / "video_only.mp4"
        if len(segment_files) == 1:
            shutil.copy(segment_files[0], video_only)
        else:
            _concat_segments(ffmpeg, segment_files, video_only)

        subtitle_clips = list(timeline.tracks.get("subtitle", []))
        burn_subtitles_enabled = not skip_subtitles and os.getenv(
            "SVG_BURN_SUBTITLES", "1"
        ).strip().lower() not in (
            "0",
            "false",
            "no",
        )
        if subtitle_clips and burn_subtitles_enabled:
            ass_path = temp_dir / "subs.ass"
            if write_ass_file(subtitle_clips, ass_path, settings):
                video_with_subs = temp_dir / "video_subs.mp4"
                burn_subtitles(
                    ffmpeg,
                    video_only,
                    ass_path,
                    video_with_subs,
                    settings,
                    run_ffmpeg=_run_ffmpeg,
                    subtitle_clips=subtitle_clips,
                )
                video_only = video_with_subs

        audio_inputs: list[tuple[Path, int, float]] = []
        for clip in timeline.tracks.get("audio", []):
            resolved = resolve_clip_media(
                store, clip, script_id=script_id, shot_by_id=shot_by_id
            )
            if not resolved:
                continue
            media = store.media_assets.get(resolved.media_id)
            if not media or media.type != MediaAssetType.AUDIO:
                continue
            local = _resolve_media_path(
                store,
                project_id=project_id,
                script_id=script_id,
                media_id=media.id,
                media_type=media.type.value,
                url=media.url,
            )
            audio_inputs.append((local, max(0, clip.start_ms), _clip_playback_rate(clip)))

        audio_path: Path | None = None
        if audio_inputs:
            audio_path = temp_dir / "mixed_audio.aac"
            _mix_audio_tracks(ffmpeg, audio_inputs, duration_sec, audio_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        _mux_av(ffmpeg, video_only, audio_path, output_path)

        return FfmpegExportResult(
            output_path=output_path,
            duration_ms=duration_ms,
            segment_count=len(segment_files),
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
