"""EditTimeline → FCP7 XMEML v5 工程文件。"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import PurePosixPath
from xml.dom import minidom

from core.edit.media_paths import ms_to_frame

from core.edit.media_paths import ms_to_frame
from core.edit.nle_export.media_bundle import MediaBundle, media_kind_for_id
from core.edit.timeline import ensure_video_layers, timeline_duration_ms
from core.models.entities import EditClip, EditTimeline
from core.store.memory import MemoryStore


def _sub(parent: ET.Element, tag: str, text: str | int | float | None = None) -> ET.Element:
    """在 parent 下创建子元素并可选写入文本。"""
    node = ET.SubElement(parent, tag)
    if text is not None:
        node.text = str(text)
    return node


def _pathurl_for_relative(rel_path: str) -> str:
    """将 ZIP 内相对路径转为 XMEML pathurl。"""
    posix = PurePosixPath(rel_path.replace("\\", "/")).as_posix()
    return f"file://localhost/{posix}"


def _clip_duration_frames(clip: EditClip, fps: int) -> int:
    """计算 clip 在时间轴上的帧数。"""
    return max(1, ms_to_frame(max(0, clip.end_ms - clip.start_ms), fps))


def _append_rate(parent: ET.Element, fps: int) -> None:
    """写入序列帧率节点。"""
    rate = _sub(parent, "rate")
    _sub(rate, "timebase", fps)
    _sub(rate, "ntsc", "FALSE")


def _append_timecode(parent: ET.Element, fps: int) -> None:
    """写入起始时间码节点。"""
    tc = _sub(parent, "timecode")
    _sub(tc, "rate")
    tc_rate = tc.find("rate")
    assert tc_rate is not None
    _sub(tc_rate, "timebase", fps)
    _sub(tc_rate, "ntsc", "FALSE")
    _sub(tc, "string", "00:00:00:00")
    _sub(tc, "frame", 0)
    _sub(tc, "displayformat", "NDF")


def _append_video_format(parent: ET.Element, width: int, height: int) -> None:
    """写入视频格式 samplecharacteristics。"""
    fmt = _sub(parent, "format")
    sc = _sub(fmt, "samplecharacteristics")
    _sub(sc, "width", width)
    _sub(sc, "height", height)
    _sub(sc, "pixelaspectratio", "square")
    _sub(sc, "fielddominance", "none")


def _append_file_node(
    parent: ET.Element,
    *,
    file_id: str,
    rel_path: str,
    name: str,
    fps: int,
    duration_frames: int,
    width: int,
    height: int,
    kind: str,
) -> None:
    """写入 clipitem 引用的 file 节点。"""
    file_node = _sub(parent, "file", None)
    file_node.set("id", file_id)
    _sub(file_node, "name", name)
    _sub(file_node, "pathurl", _pathurl_for_relative(rel_path))

    media = _sub(file_node, "media")
    if kind in ("video", "image"):
        video = _sub(media, "video")
        _sub(video, "duration", duration_frames)
        sc = _sub(video, "samplecharacteristics")
        _sub(sc, "width", width)
        _sub(sc, "height", height)
    if kind == "audio":
        audio = _sub(media, "audio")
        _sub(audio, "duration", duration_frames)
        _sub(audio, "samplecharacteristics")
        sc = audio.find("samplecharacteristics")
        assert sc is not None
        _sub(sc, "samplerate", 48000)
        _sub(sc, "depth", 16)


def _append_clipitem(
    track_node: ET.Element,
    *,
    clip: EditClip,
    clip_index: int,
    file_index: int,
    rel_path: str,
    fps: int,
    width: int,
    height: int,
    kind: str,
    store: MemoryStore,
    media_id: str,
) -> None:
    """向 track 追加单个 clipitem。"""
    start_frame = ms_to_frame(clip.start_ms, fps)
    duration_frames = _clip_duration_frames(clip, fps)
    end_frame = start_frame + duration_frames

    clip_id = f"clipitem-{clip_index}"
    file_id = f"file-{file_index}"
    file_name = PurePosixPath(rel_path).name

    item = _sub(track_node, "clipitem", None)
    item.set("id", clip_id)
    _sub(item, "name", clip.label or file_name)
    _sub(item, "duration", duration_frames)
    _sub(item, "rate")
    rate = item.find("rate")
    assert rate is not None
    _sub(rate, "timebase", fps)
    _sub(rate, "ntsc", "FALSE")
    _sub(item, "start", start_frame)
    _sub(item, "end", end_frame)
    _sub(item, "in", 0)
    _sub(item, "out", duration_frames)

    _append_file_node(
        item,
        file_id=file_id,
        rel_path=rel_path,
        name=file_name,
        fps=fps,
        duration_frames=duration_frames,
        width=width,
        height=height,
        kind=kind,
    )

    if clip.transform and kind in ("video", "image"):
        filters = _sub(item, "filters")
        effect = _sub(filters, "filter")
        _sub(effect, "effectid", "basic")
        _sub(effect, "name", "Basic Motion")
        _sub(effect, "effectcategory", "motion")
        _sub(effect, "effecttype", "motion")
        _sub(effect, "parameter")
        param = effect.find("parameter")
        assert param is not None
        _sub(param, "parameterid", "opacity")
        _sub(param, "name", "Opacity")
        _sub(param, "value", round(float(clip.transform.opacity or 1.0) * 100, 2))


def write_xmeml(
    store: MemoryStore,
    timeline: EditTimeline,
    bundle: MediaBundle,
    *,
    sequence_name: str,
    fps: int,
    width: int,
    height: int,
) -> str:
    """生成 FCP7 XMEML v5 字符串。"""
    timeline = ensure_video_layers(timeline)
    duration_ms = timeline_duration_ms(timeline)
    sequence_frames = max(1, ms_to_frame(duration_ms, fps))

    root = ET.Element("xmeml")
    root.set("version", "5")
    sequence = _sub(root, "sequence", None)
    sequence.set("id", "sequence-1")

    _sub(sequence, "name", sequence_name or timeline.script_id)
    _sub(sequence, "duration", sequence_frames)
    _append_rate(sequence, fps)
    _append_timecode(sequence, fps)

    media = _sub(sequence, "media")
    video = _sub(media, "video")
    _append_video_format(video, width, height)

    clip_counter = 1
    file_counter = 1

    for layer in sorted(timeline.video_layers, key=lambda item: item.z_index):
        track_node = _sub(video, "track")
        for clip in sorted(layer.clips, key=lambda c: c.start_ms):
            media_id = bundle.clip_media_id.get(clip.id)
            if not media_id:
                continue
            rel_path = bundle.path_by_media_id.get(media_id)
            if not rel_path:
                continue
            kind = media_kind_for_id(store, media_id)
            _append_clipitem(
                track_node,
                clip=clip,
                clip_index=clip_counter,
                file_index=file_counter,
                rel_path=rel_path,
                fps=fps,
                width=width,
                height=height,
                kind=kind,
                store=store,
                media_id=media_id,
            )
            clip_counter += 1
            file_counter += 1

    audio_clips = timeline.tracks.get("audio", [])
    if audio_clips:
        audio = _sub(media, "audio")
        audio_track = _sub(audio, "track")
        for clip in sorted(audio_clips, key=lambda c: c.start_ms):
            media_id = bundle.clip_media_id.get(clip.id)
            if not media_id:
                continue
            rel_path = bundle.path_by_media_id.get(media_id)
            if not rel_path:
                continue
            _append_clipitem(
                audio_track,
                clip=clip,
                clip_index=clip_counter,
                file_index=file_counter,
                rel_path=rel_path,
                fps=fps,
                width=width,
                height=height,
                kind="audio",
                store=store,
                media_id=media_id,
            )
            clip_counter += 1
            file_counter += 1

    xml_bytes = ET.tostring(root, encoding="utf-8")
    parsed = minidom.parseString(xml_bytes)
    pretty = parsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n' + pretty.split("\n", 1)[1]
