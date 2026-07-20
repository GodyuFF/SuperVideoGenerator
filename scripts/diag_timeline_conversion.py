"""诊断 EditTimeline → OpenCut loadFromSvf 转换时序。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TICKS_PER_SECOND = 120_000


def ms_to_ticks(ms: float) -> int:
    """毫秒转 OpenCut ticks。"""
    return round((ms / 1000) * TICKS_PER_SECOND)


def ticks_to_ms(ticks: int) -> int:
    """OpenCut ticks 转毫秒。"""
    return round((ticks / TICKS_PER_SECOND) * 1000)


def compute_trim(clip_ms: int, source_ms: int, *, pad_audio: bool = False) -> tuple[int, int, int]:
    """模拟 computeMediaTrimFields：返回 trimEnd(ms)、sourceDuration(ms)、可见时长(ms)。"""
    clip_ticks = ms_to_ticks(clip_ms)
    source_ticks = ms_to_ticks(source_ms)
    if clip_ticks >= source_ticks:
        eff_ticks = max(source_ticks, clip_ticks) if pad_audio else source_ticks
        return 0, ticks_to_ms(eff_ticks), clip_ms
    trim_end_ms = ticks_to_ms(source_ticks - clip_ticks)
    return trim_end_ms, ticks_to_ms(source_ticks), clip_ms


def classic_layout_matches_api(clip: dict, classic: dict) -> bool:
    """与 svfProjectAdapter.classicLayoutMatchesApi 一致。"""
    start = clip.get("start_ms", 0)
    end = clip.get("end_ms", start + 1000)
    api_dur = end - start
    classic_start = ticks_to_ms(classic.get("startTime", 0))
    classic_dur = ticks_to_ms(classic.get("duration", 0))
    if abs(classic_start - start) > 500:
        return False
    if classic_dur < api_dur * 0.7:
        return False
    if abs(classic_start + classic_dur - end) > 500:
        return False
    return True


def is_classic_layout_locked(clip: dict) -> bool:
    """与 svfProjectAdapter.isClassicLayoutLocked 一致。"""
    meta = clip.get("metadata") or {}
    if meta.get("user_locked"):
        return True
    classic = meta.get("classic")
    if not classic or meta.get("edited_by") != "user":
        return False
    if not isinstance(classic.get("startTime"), (int, float)):
        return False
    if not isinstance(classic.get("duration"), (int, float)):
        return False
    return classic_layout_matches_api(clip, classic)


def resolve_audio_clip_duration_ms(
    clip: dict,
    element_type: str,
    clip_duration_ms: int,
    source_duration_ms: int,
) -> int:
    """与 resolveAudioClipDurationMs 一致。"""
    if element_type != "audio":
        return clip_duration_ms
    if is_classic_layout_locked(clip):
        return clip_duration_ms
    if source_duration_ms <= clip_duration_ms + 50:
        return clip_duration_ms
    return source_duration_ms


def clip_to_element_projection(
    clip: dict,
    media_type: str,
    dur_by_id: dict[str, int],
) -> dict:
    """模拟 clipToElement 的 start/duration 输出（不含 transform）。"""
    start = clip.get("start_ms", 0)
    end = clip.get("end_ms", start + 1000)
    clip_ms = end - start
    media_id = clip.get("asset_ref")
    source_ms = dur_by_id.get(media_id or "", clip_ms)
    element_type = "video" if media_type == "video" else "audio" if media_type == "audio" else "image"
    visible_ms = resolve_audio_clip_duration_ms(clip, element_type, clip_ms, source_ms)
    trim_end, source_dur_ms, _ = compute_trim(
        visible_ms,
        source_ms,
        pad_audio=element_type == "audio",
    )

    base_start = start
    base_duration = visible_ms
    locked = is_classic_layout_locked(clip)
    classic = (clip.get("metadata") or {}).get("classic")
    final_start = base_start
    final_duration = base_duration
    merge_source = "api"
    if classic and isinstance(classic, dict):
        if locked:
            final_start = ticks_to_ms(classic.get("startTime", 0))
            final_duration = ticks_to_ms(classic.get("duration", 0))
            merge_source = "classic_locked"
        else:
            merge_source = "classic_decorations_only"

    return {
        "id": clip.get("id"),
        "track": media_type,
        "api_start": start,
        "api_end": end,
        "api_dur": clip_ms,
        "media_id": media_id,
        "media_dur_ms": source_ms,
        "trim_end_ms": trim_end,
        "source_dur_ms": source_dur_ms,
        "base_start": base_start,
        "base_duration": base_duration,
        "final_start": final_start,
        "final_duration": final_duration,
        "final_end": final_start + final_duration,
        "locked": locked,
        "merge_source": merge_source,
    }


def dump_snapshot_elements(label: str, track: object) -> list[dict]:
    """解析 classic_project 快照中的 element 时序。"""
    elements: list = []
    if isinstance(track, dict):
        elements = track.get("elements") or []
    elif isinstance(track, list) and track and isinstance(track[0], dict):
        elements = track[0].get("elements") or []
    rows = []
    for el in elements:
        st = ticks_to_ms(el.get("startTime", 0))
        du = ticks_to_ms(el.get("duration", 0))
        rows.append(
            {
                "label": label,
                "id": el.get("id"),
                "start": st,
                "end": st + du,
                "dur": du,
                "type": el.get("type"),
            }
        )
    return rows


def main() -> int:
    """读取 timeline + media JSON，打印 API 与投影对比。"""
    root = Path(__file__).resolve().parents[1]
    tl_path = root / "data" / "temp_etl_diag.json"
    media_path = root / "data" / "temp_media_diag.json"
    if len(sys.argv) >= 3:
        tl_path = Path(sys.argv[1])
        media_path = Path(sys.argv[2])

    tl = json.loads(tl_path.read_text(encoding="utf-8"))
    media = json.loads(media_path.read_text(encoding="utf-8"))
    dur_by_id = {m["id"]: m.get("duration_ms") or 0 for m in media}

    print("=== EditTimeline API ===")
    print(f"timeline_id: {tl.get('timeline_id')}")
    print(f"duration_ms: {tl.get('duration_ms')}  revision: {tl.get('revision')}")

    projections: list[dict] = []
    for layer in tl.get("video_layers") or []:
        for clip in layer.get("clips") or []:
            projections.append(clip_to_element_projection(clip, "video", dur_by_id))

    for clip in (tl.get("tracks") or {}).get("audio") or []:
        projections.append(clip_to_element_projection(clip, "audio", dur_by_id))

    max_api = max((p["api_end"] for p in projections), default=0)
    max_base = max((p["base_start"] + p["base_duration"] for p in projections), default=0)
    max_final = max((p["final_end"] for p in projections), default=0)

    print("\n=== clipToElement 投影 ===")
    for p in projections:
        flag = p["merge_source"]
        if p["trim_end_ms"] > 0 and not p["locked"]:
            flag += f" TRIM(source={p['media_dur_ms']}ms)"
        print(
            f"{p['track']:5} {p['id']:16} "
            f"API {p['api_start']:5}-{p['api_end']:5} ({p['api_dur']:4}ms) "
            f"→ final {p['final_start']:5}-{p['final_end']:5} ({p['final_duration']:4}ms) "
            f"[{flag}]"
        )

    print("\n=== 总时长对比 ===")
    print(f"API clips max end:     {max_api} ms")
    print(f"base projection end:   {max_base} ms")
    print(f"after classic merge:   {max_final} ms")
    print(f"stored duration_ms:    {tl.get('duration_ms')} ms")
    delta = max_final - tl.get("duration_ms", 0)
    if abs(delta) > 500:
        print(f"⚠ 投影与存储 duration_ms 偏差 {delta:+d} ms")
    elif max_final < max_api - 500:
        print(f"⚠ 投影终点短于 API 终点 {(max_api - max_final)} ms — 转换会截断成片")

    cp = (tl.get("metadata") or {}).get("classic_project") or {}
    scenes = cp.get("scenes") or []
    if scenes:
        tracks = scenes[0].get("tracks") or {}
        snap_rows: list[dict] = []
        snap_rows.extend(dump_snapshot_elements("main", tracks.get("main")))
        snap_rows.extend(dump_snapshot_elements("audio", tracks.get("audio")))
        if snap_rows:
            snap_max = max(r["end"] for r in snap_rows)
            print(f"\n=== metadata.classic_project 快照 ===")
            print(f"snapshot max end: {snap_max} ms")
            for r in snap_rows:
                print(
                    f"  {r['label']:8} {r['id']:16} "
                    f"{r['start']:5}-{r['end']:5} ({r['dur']:4}ms) type={r['type']}"
                )
            if snap_max < tl.get("duration_ms", 0) - 500:
                print(
                    f"⚠ classic_project 快照终点 {snap_max}ms 短于 duration_ms "
                    f"{tl.get('duration_ms')}ms — applySnapshotDecorationsToScenes 可能压短预览"
                )

    # 输出 canvas 用 JSON
    out = {
        "timeline_id": tl.get("timeline_id"),
        "duration_ms": tl.get("duration_ms"),
        "revision": tl.get("revision"),
        "max_api_end": max_api,
        "max_projected_end": max_final,
        "clips": [
            {
                "id": p["id"],
                "track": p["track"],
                "apiStart": p["api_start"],
                "apiEnd": p["api_end"],
                "projStart": p["final_start"],
                "projEnd": p["final_end"],
                "mediaDur": p["media_dur_ms"],
                "issue": (
                    "trim"
                    if p["trim_end_ms"] > 0 and not p["locked"]
                    else "locked"
                    if p["locked"]
                    else "ok"
                ),
            }
            for p in projections
        ],
        "snapshot": snap_rows if scenes else [],
    }
    out_path = root / "data" / "timeline_conversion_diag.json"
    # 模拟无 classic 锁 + 浏览器 probe 偏短
    short_probe: dict[str, int] = {
        m["id"]: 2500 for m in media if m.get("type") == "audio"
    }
    short_rows: list[dict] = []
    for layer in tl.get("video_layers") or []:
        for clip in layer.get("clips") or []:
            stripped = {**clip, "metadata": {}}
            short_rows.append(
                clip_to_element_projection(stripped, "video", short_probe),
            )
    for clip in (tl.get("tracks") or {}).get("audio") or []:
        stripped = {**clip, "metadata": {}}
        short_rows.append(
            clip_to_element_projection(stripped, "audio", short_probe),
        )
    short_max = max((r["final_end"] for r in short_rows), default=0)
    out["shortProbeScenario"] = {
        "probe_audio_ms": 2500,
        "max_projected_end": short_max,
        "clips": [
            {
                "id": r["id"],
                "track": r["track"],
                "apiEnd": r["api_end"],
                "projEnd": r["final_end"],
                "trimEndMs": r["trim_end_ms"],
            }
            for r in short_rows
        ],
    }

    # 模拟历史错误：紧凑顺排 ~9s 且 edited_by=user（修复前应被 classicLayoutMatchesApi 拒绝）
    packed_starts = [0, 1395, 2789, 4184, 5578, 6973, 8367, 9762]
    packed_durs = [1395, 1394, 1395, 1394, 1395, 1394, 1395, 1394]
    packed_max = 0
    packed_rows: list[dict] = []
    idx = 0
    for layer in tl.get("video_layers") or []:
        for clip in layer.get("clips") or []:
            s, d = packed_starts[idx], packed_durs[idx]
            idx += 1
            classic = {"startTime": ms_to_ticks(s), "duration": ms_to_ticks(d)}
            c2 = {
                **clip,
                "metadata": {
                    "edited_by": "user",
                    "classic": classic,
                },
            }
            p = clip_to_element_projection(c2, "video", dur_by_id)
            packed_rows.append(p)
            packed_max = max(packed_max, p["final_end"])
    for clip in (tl.get("tracks") or {}).get("audio") or []:
        s, d = packed_starts[idx], packed_durs[idx]
        idx += 1
        classic = {"startTime": ms_to_ticks(s), "duration": ms_to_ticks(d)}
        c2 = {
            **clip,
            "metadata": {
                "edited_by": "user",
                "classic": classic,
            },
        }
        p = clip_to_element_projection(c2, "audio", dur_by_id)
        packed_rows.append(p)
        packed_max = max(packed_max, p["final_end"])
    out["packedBugScenario"] = {
        "max_projected_end": packed_max,
        "locked_count": sum(1 for r in packed_rows if r["locked"]),
        "clips": [
            {
                "id": r["id"],
                "track": r["track"],
                "apiEnd": r["api_end"],
                "projEnd": r["final_end"],
                "locked": r["locked"],
            }
            for r in packed_rows
        ],
    }

    print("\n=== 模拟 probe 偏短 (audio=2500ms, 无 classic 锁) ===")
    print(f"投影 max end: {short_max} ms (API {max_api} ms)")
    for r in short_rows:
        note = "pad OK" if r["final_end"] == r["api_end"] else "SHORT"
        print(
            f"{r['track']:5} {r['id']:16} API end {r['api_end']:5} "
            f"→ {r['final_end']:5} trimEnd={r['trim_end_ms']:4} [{note}]"
        )

    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n诊断 JSON 已写入 {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
