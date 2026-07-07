"""storyboard_agent tools handlers."""

from __future__ import annotations

import json

from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.result import ToolResult
from core.llm.tools.storyboard.timeline_handler import (
    handle_create_shots,
    handle_load_context_enriched,
    handle_persist_plan,
)
from core.store.memory import MemoryStore


def handle_get_plan(store: MemoryStore, ctx: AgentRunContext, args: dict) -> ToolResult:
    vp = store.get_video_plan_for_script(ctx.script_id)
    if not vp:
        structured = {
            "shot_count": 0,
            "shots": [],
            "message": "当前无视频计划稿。请先 load_context 后 create_shots。",
        }
        obs_prefix = str(args.get("observation", "")).strip()
        obs = obs_prefix or structured["message"]
        return ToolResult(
            observation=f"{obs}\n\n{json.dumps(structured, ensure_ascii=False, indent=2)}",
            structured=structured,
        )
    shots = [
        {
            "id": s.id,
            "order": s.order,
            "duration_ms": s.duration_ms,
            "camera_motion": s.camera_motion,
            "narration_text": s.narration_text,
            "asset_refs": s.asset_refs,
        }
        for s in sorted(vp.shots, key=lambda x: x.order)
    ]
    structured = {
        "plan_id": vp.id,
        "mode": vp.mode.value,
        "shot_count": len(shots),
        "shots": shots,
    }
    obs_prefix = (
        str(args.get("observation", "")).strip()
        or f"计划稿 {vp.id}，共 {len(shots)} 镜。"
    )
    return ToolResult(
        observation=f"{obs_prefix}\n\n{json.dumps(structured, ensure_ascii=False, indent=2)}",
        structured=structured,
    )


HANDLERS = {
    "get_plan": handle_get_plan,
    "load_context": handle_load_context_enriched,
    "create_shots": handle_create_shots,
    "persist_plan": handle_persist_plan,
}
