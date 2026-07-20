"""从 VideoPlan 确定性提取旁白。"""

from __future__ import annotations

from typing import Any

from core.store.memory import MemoryStore
from core.tts.planned_synthesis import build_voice_segments_from_shot


def build_narration_payload(store: MemoryStore, script_id: str) -> dict[str, Any]:
    """从计划稿镜内 voice clip 提取旁白条目。"""
    plan = store.get_video_plan_for_script(script_id)
    if plan is None or not plan.shots:
        return {
            "valid": False,
            "error": "未找到分镜计划稿，请先完成 storyboard 步骤。",
            "line_count": 0,
            "items": [],
        }

    items: list[dict[str, Any]] = []
    for shot in sorted(plan.shots, key=lambda s: s.order):
        voice_segments = build_voice_segments_from_shot(shot)
        text = "".join(seg["text"] for seg in voice_segments).strip()
        if not text:
            continue
        item: dict[str, Any] = {
            "shot_id": shot.id,
            "order": shot.order,
            "text": text,
            "duration_ms": max(int(shot.duration_ms), 1000),
            "voice_segments": voice_segments,
        }
        if len(voice_segments) > 1:
            item["has_multi_voice"] = True
        items.append(item)

    return {
        "valid": bool(items),
        "plan_id": plan.id,
        "line_count": len(items),
        "items": items,
    }


def format_narration_observation(payload: dict[str, Any]) -> str:
    """格式化旁白提取观察文本。"""
    if not payload.get("valid"):
        return str(payload.get("error") or "未提取到旁白文案。")
    count = int(payload.get("line_count", 0))
    return f"已从计划稿提取 {count} 条旁白（按镜头 order 排序）。"
