"""从 VideoPlan 确定性提取旁白。"""

from __future__ import annotations

from typing import Any

from core.store.memory import MemoryStore


def build_narration_payload(store: MemoryStore, script_id: str) -> dict[str, Any]:
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
        text = str(shot.narration_text or "").strip()
        if not text:
            continue
        items.append(
            {
                "shot_id": shot.id,
                "order": shot.order,
                "text": text,
                "duration_ms": max(int(shot.duration_ms), 1000),
            }
        )

    return {
        "valid": bool(items),
        "plan_id": plan.id,
        "line_count": len(items),
        "items": items,
    }


def format_narration_observation(payload: dict[str, Any]) -> str:
    if not payload.get("valid"):
        return str(payload.get("error") or "未提取到旁白文案。")
    count = int(payload.get("line_count", 0))
    return f"已从计划稿提取 {count} 条旁白（按镜头 order 排序）。"
