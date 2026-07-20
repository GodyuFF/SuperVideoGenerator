"""媒体类 tool 共享 handler 逻辑。"""

from __future__ import annotations

from typing import Any

from core.edit.shot_query import serialize_shots_for_agent
from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.result import ToolResult
from core.llm.tools.shared.media_list import (
    build_media_list_payload,
    format_media_list_payload,
)
from core.models.entities import MediaAssetType
from core.store.memory import MemoryStore
from core.store.persist import schedule_save


def apply_agent_action(
    store: MemoryStore,
    ctx: AgentRunContext,
    args: dict[str, Any],
    *,
    agent: str,
    action: str,
) -> ToolResult:
    from core.llm.agent.llm_action import apply_action_result

    outputs_before = list(ctx.outputs)
    observation = apply_action_result(store, agent, action, ctx, args)
    schedule_save(store, immediate=True)
    structured: dict[str, Any] = {
        "action": action,
        "summary": observation[:200],
    }
    if action == "create_frames":
        links = ctx.work_context.get("_frame_links")
        if isinstance(links, list) and links:
            structured["frame_links"] = links
    if action in ("create_shots", "create_frames", "persist_plan"):
        pending = ctx.work_context.get("_pending_shots")
        if isinstance(pending, list):
            structured["shot_count"] = len(pending)
            structured["shots"] = serialize_shots_for_agent(pending)
            if action == "create_shots":
                structured["source"] = "pending"
                structured["message"] = (
                    "create_shots 已解析镜头；请用下方 sub_shots[].id 作为 create_frames.sub_shot_id，"
                    "勿自造 ID。"
                )
        elif action == "persist_plan":
            vp = store.get_video_plan_for_script(ctx.script_id)
            if vp:
                structured["shot_count"] = len(vp.shots)
                structured["shots"] = serialize_shots_for_agent(vp.shots)
                structured["source"] = "persisted"
    new_outputs = [o for o in ctx.outputs if o not in outputs_before]
    if new_outputs:
        structured["output_count"] = len(new_outputs)
        structured["asset_ids"] = [o.asset_id for o in new_outputs if o.asset_id]
    obs_out = observation
    if action == "create_shots" and structured.get("shots"):
        import json

        msg = structured.get("message") or observation
        obs_out = f"{msg}\n\n{json.dumps(structured, ensure_ascii=False, indent=2)}"
    return ToolResult(
        observation=obs_out,
        structured=structured,
        outputs=new_outputs,
    )


def read_media_list(
    store: MemoryStore,
    ctx: AgentRunContext,
    args: dict[str, Any],
    *,
    media_type: MediaAssetType,
) -> ToolResult:
    payload = build_media_list_payload(store, ctx.script_id, media_type)
    observation = format_media_list_payload(payload)
    return ToolResult(observation=observation, structured=payload)


def make_write_handler(agent: str, action: str):
    def handler(store, ctx, args):
        return apply_agent_action(store, ctx, args, agent=agent, action=action)

    return handler
