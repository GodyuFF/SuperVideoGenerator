"""分镜看板数据诊断：对比 VideoPlan、TTS 绑定与 BoardBuilder 输出。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.board.builder import BoardBuilder
from core.edit.shot_detail_sync import sync_plan_from_tts
from core.edit.timeline import build_tts_by_shot
from core.models.entities import Project, Script
from core.store.asset_disk_sync import BUNDLE_FILENAME, _merge_bundle_into_store
from core.store.memory import MemoryStore
from core.store.persist import load_store
from core.store.project_paths import PROJECTS_ROOT


def _find_bundle(script_id: str) -> Path | None:
    """按 script_id 定位 store_bundle.json。"""
    if not PROJECTS_ROOT.is_dir():
        return None
    for proj_dir in PROJECTS_ROOT.iterdir():
        if not proj_dir.is_dir():
            continue
        bundle = proj_dir / "scripts" / script_id / BUNDLE_FILENAME
        if bundle.is_file():
            return bundle
    return None


def load_store_for_script(script_id: str) -> tuple[MemoryStore, str, str]:
    """加载 dev_store 并合并指定剧本 bundle，返回 store、project_id、script_id。"""
    store = MemoryStore()
    load_store(store)
    bundle_path = _find_bundle(script_id)
    if bundle_path is None:
        raise FileNotFoundError(f"未找到剧本 bundle: {script_id}")

    raw = json.loads(bundle_path.read_text(encoding="utf-8"))
    project_id = str(raw.get("project_id") or bundle_path.parent.parent.parent.name)
    bundle_script_id = str(raw.get("script_id") or script_id)

    if store.get_project(project_id) is None:
        store.add_project(Project(id=project_id, title=project_id))
    if store.get_script(bundle_script_id) is None:
        store.add_script(
            Script(project_id=project_id, id=bundle_script_id, title=bundle_script_id)
        )

    _merge_bundle_into_store(store, raw)

    for pid, item in (raw.get("video_plans") or {}).items():
        from core.models.entities import VideoPlan

        try:
            store.video_plans[pid] = VideoPlan.model_validate(item)
        except (ValueError, TypeError):
            continue

    for mid, item in (raw.get("media_assets") or {}).items():
        from core.models.entities import MediaAsset

        try:
            store.media_assets[mid] = MediaAsset.model_validate(item)
        except (ValueError, TypeError):
            continue

    return store, project_id, bundle_script_id


def diagnose_shot_board_item(
    shot: dict[str, Any],
    *,
    script_id: str,
    has_tts: bool,
    has_narration: bool,
) -> tuple[bool, bool, list[str]]:
    """判定单镜数据层与展示层是否正常，并收集建议。"""
    data_issues: list[str] = []
    display_issues: list[str] = []

    start_ms = int(shot.get("start_ms") or 0)
    end_ms = int(shot.get("end_ms") or 0)
    duration_ms = int(shot.get("duration_ms") or 0)
    actual_duration_ms = int(
        shot.get("actual_duration_ms")
        or shot.get("tts_duration_ms")
        or shot.get("duration_ms")
        or 0
    )
    subtitle_lines = shot.get("subtitle_lines") or []
    display_instructions = str(shot.get("review_note") or shot.get("display_instructions") or "").strip()
    camera_motion = str(shot.get("camera_motion") or "")
    camera_label = str(shot.get("camera_motion_label") or "")
    frame_url = str(shot.get("frame_preview_url") or "")

    if has_tts and has_narration and not subtitle_lines:
        data_issues.append("缺字幕行（需 sync-from-tts 或看板懒同步）")
    if has_tts and actual_duration_ms <= 0:
        data_issues.append("缺 actual_duration_ms")
    if has_tts and duration_ms > 0 and actual_duration_ms > 0:
        if abs(duration_ms - actual_duration_ms) > 500 and not subtitle_lines:
            data_issues.append("duration_ms 未按 TTS 实测调整")
    if end_ms <= start_ms and duration_ms > 0:
        data_issues.append("时间轴 end_ms 异常")
    if not display_instructions:
        display_issues.append("展示说明为空（需 delegate_shot_detail 填写 review_note）")
    if camera_motion and not camera_label:
        display_issues.append("缺 camera_motion_label（需重启 API 加载新 builder）")
    if camera_motion in ("slow_zoom_in", "slow_pan", "gentle_push_in", "slow_pan_right"):
        data_issues.append(f"运镜仍为别名 {camera_motion}（sync-from-tts 可规范化）")
    if not frame_url and (shot.get("asset_refs") or {}).get("frame"):
        display_issues.append("有 frame 资产但无预览图")

    data_ok = not data_issues
    display_ok = not display_issues
    hints: list[str] = []
    if data_issues:
        hints.append(
            f"POST /api/projects/{{pid}}/scripts/{script_id}/video-plan/sync-from-tts"
        )
    if display_issues:
        hints.append("对话触发 delegate_shot_detail 补全展示说明")
    return data_ok, display_ok, data_issues + display_issues + hints


def _shot_voice_text(shot) -> str:
    """拼接镜内 voice 音频 clip 文案。"""
    return "".join(
        c.text.strip()
        for t in shot.audio_tracks
        if t.kind == "voice"
        for c in t.clips
        if c.text.strip()
    )


def run_diagnosis(store: MemoryStore, project_id: str, script_id: str) -> dict[str, Any]:
    """执行完整诊断并返回结构化结论。"""
    plan_before = store.get_video_plan_for_script(script_id)
    if not plan_before or not plan_before.shots:
        raise ValueError(f"剧本 {script_id} 无 VideoPlan")

    tts_by_shot = build_tts_by_shot(store, script_id)
    view = BoardBuilder(store).build("storyboard", project_id, script_id)
    plan = store.get_video_plan_for_script(script_id)
    if not plan:
        plan = plan_before
    items_by_id = {str(i["id"]): i for i in view.items}

    shot_reports: list[dict[str, Any]] = []
    all_data_ok = True
    all_display_ok = True
    cumulative_ok = True
    prev_end = 0

    for shot in sorted(plan.shots, key=lambda s: s.order):
        item = items_by_id.get(shot.id, {})
        has_tts = shot.id in tts_by_shot
        has_narration = bool(_shot_voice_text(shot))
        subtitle_count = len(shot.subtitles)
        board_subs = item.get("subtitle_lines") or []

        start_ms = int(item.get("start_ms") or 0)
        end_ms = int(item.get("end_ms") or 0)
        if shot.order > 0 and start_ms < prev_end:
            cumulative_ok = False
        if end_ms > start_ms:
            prev_end = end_ms

        if has_tts and has_narration and subtitle_count == 0 and len(board_subs) == 0:
            all_data_ok = False

        data_ok, display_ok, issues = diagnose_shot_board_item(
            {**item, "script_id": script_id},
            script_id=script_id,
            has_tts=has_tts,
            has_narration=has_narration,
        )
        if has_tts and has_narration and subtitle_count == 0 and len(board_subs) == 0:
            data_ok = False
            if "缺字幕行（需 sync-from-tts 或看板懒同步）" not in issues:
                issues.insert(0, "缺字幕行（需 sync-from-tts 或看板懒同步）")
        all_data_ok = all_data_ok and data_ok
        all_display_ok = all_display_ok and display_ok

        from core.edit.shot_detail_sync import resolve_effective_camera_motion
        from core.edit.shot_duration import resolve_effective_shot_duration_ms

        effective_motion = resolve_effective_camera_motion(shot)
        actual_ms = resolve_effective_shot_duration_ms(store, shot, tts_by_shot)
        shot_reports.append(
            {
                "shot_id": shot.id,
                "order": shot.order,
                "duration_ms": shot.duration_ms,
                "actual_duration_ms": actual_ms,
                "subtitle_lines_count": max(subtitle_count, len(board_subs)),
                "board_subtitle_lines_count": len(board_subs),
                "start_ms": start_ms,
                "end_ms": end_ms,
                "tts_bound": has_tts,
                "display_instructions_empty": not str(item.get("display_instructions") or item.get("review_note") or "").strip(),
                "frame_preview_url": item.get("frame_preview_url") or "",
                "camera_motion": effective_motion,
                "camera_motion_label": item.get("camera_motion_label"),
                "data_ok": data_ok,
                "display_ok": display_ok,
                "issues": issues,
            }
        )

    return {
        "project_id": project_id,
        "script_id": script_id,
        "plan_id": plan.id,
        "detail_revision": plan.detail_revision,
        "shot_count": len(shot_reports),
        "tts_shot_count": len(tts_by_shot),
        "cumulative_timeline_ok": cumulative_ok,
        "data_ok": all_data_ok and cumulative_ok,
        "display_ok": all_display_ok,
        "shots": shot_reports,
        "suggestions": _build_suggestions(all_data_ok and cumulative_ok, all_display_ok, script_id),
    }


def _build_suggestions(data_ok: bool, display_ok: bool, script_id: str) -> list[str]:
    """汇总修复建议命令。"""
    suggestions: list[str] = []
    if not data_ok:
        suggestions.append(
            f"POST .../scripts/{script_id}/video-plan/sync-from-tts"
        )
        suggestions.append("重启 API 后刷新分镜 Tab（触发 ensure_storyboard_tts_sync + 落盘）")
    if not display_ok:
        suggestions.append("主编排 delegate_shot_detail（展示说明 / 画面细节）")
    return suggestions


def print_report(report: dict[str, Any]) -> None:
    """将诊断结果打印为人类可读文本。"""
    print(f"剧本: {report['script_id']}  项目: {report['project_id']}")
    print(f"镜头数: {report['shot_count']}  TTS 绑定: {report['tts_shot_count']}")
    print(
        f"累加时间: {'OK' if report['cumulative_timeline_ok'] else '异常'}  "
        f"数据层: {'OK' if report['data_ok'] else '有问题'}  "
        f"展示层: {'OK' if report['display_ok'] else '有问题'}"
    )
    print("-" * 60)
    for shot in report["shots"]:
        print(
            f"镜 {shot['order'] + 1} ({shot['shot_id']})  "
            f"dur={shot['duration_ms']}ms actual={shot['actual_duration_ms']}ms  "
            f"subs={shot['subtitle_lines_count']}  "
            f"time={shot['start_ms']}–{shot['end_ms']}ms  "
            f"tts={'Y' if shot['tts_bound'] else 'N'}"
        )
        if shot["issues"]:
            for issue in shot["issues"]:
                print(f"  - {issue}")
    if report["suggestions"]:
        print("-" * 60)
        print("建议:")
        for s in report["suggestions"]:
            print(f"  · {s}")


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(description="分镜看板数据诊断")
    parser.add_argument("script_id", help="剧本 ID，如 script_16b48abce85d")
    parser.add_argument(
        "--sync",
        action="store_true",
        help="诊断前执行 sync_plan_from_tts 并写回 dev_store",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    store, project_id, script_id = load_store_for_script(args.script_id)
    if args.sync:
        result = sync_plan_from_tts(store, script_id)
        from core.store.persist import save_store

        save_store(store)
        if not args.json:
            print(f"已 sync-from-tts: {result}")
            print()

    report = run_diagnosis(store, project_id, script_id)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)
    return 0 if report["data_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
