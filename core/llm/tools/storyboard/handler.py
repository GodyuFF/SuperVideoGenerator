"""storyboard_agent tools handlers."""



from __future__ import annotations



import json



from core.edit.shot_query import serialize_shots_for_agent

from core.llm.agent.react_core import AgentRunContext

from core.llm.tools.result import ToolResult

from core.llm.tools.storyboard.timeline_handler import (

    handle_create_frames,

    handle_create_shots,

    handle_create_video_clips,

    handle_load_context_enriched,

    handle_persist_plan,

)

from core.store.memory import MemoryStore





def _shots_payload_from_plan(vp) -> list[dict]:

    """从已持久化 VideoPlan 构建 get_plan 镜头 JSON。"""

    return [

        {

            "id": s.id,

            "order": s.order,

            "duration_ms": s.duration_ms,

            "title": s.title,

            "summary": s.summary,

            "sub_shots": [v.model_dump() for v in s.sub_shots],

            "audio_tracks": [t.model_dump() for t in s.audio_tracks],

            "subtitles": [sub.model_dump() for sub in s.subtitles],

        }

        for s in sorted(vp.shots, key=lambda x: x.order)

    ]





def handle_get_plan(store: MemoryStore, ctx: AgentRunContext, args: dict) -> ToolResult:

    """读取视频计划稿；persist 前回退返回 work_context 中的待保存镜头。"""

    vp = store.get_video_plan_for_script(ctx.script_id)

    pending = ctx.work_context.get("_pending_shots")

    if vp:

        shots = _shots_payload_from_plan(vp)

        structured = {

            "source": "persisted",

            "plan_id": vp.id,

            "mode": vp.mode.value,

            "shot_count": len(shots),

            "shots": shots,

        }

        obs_prefix = (

            str(args.get("observation", "")).strip()

            or f"计划稿 {vp.id}，共 {len(shots)} 镜。"

        )

    elif isinstance(pending, list) and pending:

        shots = serialize_shots_for_agent(pending)

        structured = {

            "source": "pending",

            "shot_count": len(shots),

            "shots": shots,

            "message": "计划稿尚未 persist_plan；以下为 create_shots 后系统生成的 shot/sub_shot ID。",

        }

        obs_prefix = (

            str(args.get("observation", "")).strip()

            or structured["message"]

        )

    else:

        structured = {

            "source": "empty",

            "shot_count": 0,

            "shots": [],

            "message": "当前无视频计划稿。请先 load_context 后 create_shots。",

        }

        obs_prefix = str(args.get("observation", "")).strip() or structured["message"]

    return ToolResult(

        observation=f"{obs_prefix}\n\n{json.dumps(structured, ensure_ascii=False, indent=2)}",

        structured=structured,

    )





HANDLERS = {

    "get_plan": handle_get_plan,

    "load_context": handle_load_context_enriched,

    "create_shots": handle_create_shots,

    "create_frames": handle_create_frames,

    "create_video_clips": handle_create_video_clips,

    "persist_plan": handle_persist_plan,

}

