"""Agent 可控剪辑工具处理实现。

所有写操作必须经 core.edit.timeline_service.patch_timeline 写入 EditTimeline
（video_layers + tracks），禁止旁路修改 VideoPlan 代替剪辑编排。

每个 handler 接收:
- store: MemoryStore
- ctx: AgentRunContext
- args: dict[str, Any] (LLM 生成的工具参数)

返回 ToolResult(observation=str, structured=dict, ok=bool)
"""

from __future__ import annotations

import json
from typing import Any

from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.result import ToolResult
from core.models.entities import EditClip, MediaAssetType, StepOutput
from core.store.memory import MemoryStore
from core.store.persist import schedule_save
from core.edit.timeline import (
    _effective_audio_media_duration_ms,
    build_timeline_layer_summary,
    format_layer_summary_text,
    timeline_board_items,
    timeline_duration_ms,
)
from core.edit.timeline_service import patch_timeline
from core.llm.tools.shared.media_list import resolve_media_access


def _script_from_ctx(ctx: AgentRunContext) -> str:
    return str(ctx.work_context.get("script_id") or ctx.script_id)


def _project_from_ctx(ctx: AgentRunContext) -> str:
    return str(ctx.work_context.get("project_id", ""))


def _clip_to_raw(clip: EditClip) -> dict[str, Any]:
    """将现有 clip 全量序列化为 PATCH body，避免丢失 source_refs/motion/过渡等字段。"""
    raw = clip.model_dump()
    meta = dict(raw.get("metadata") or {})
    meta.setdefault("edited_by", "agent")
    raw["metadata"] = meta
    return raw


def _resolve_media_default_duration_ms(store: MemoryStore, media) -> int:
    """未显式指定时长时读取素材真实时长；音频优先本地探测，兜底 3000ms。"""
    if media.type == MediaAssetType.AUDIO:
        probed = _effective_audio_media_duration_ms(store, media)
        if probed > 0:
            return probed
    meta_ms = int((media.metadata or {}).get("duration_ms") or 0)
    if meta_ms > 0:
        return meta_ms
    return 3000


def handle_get_edit_timeline(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """查询当前时间轴状态。"""
    del args
    script_id = _script_from_ctx(ctx)

    timeline = store.get_edit_timeline_for_script(script_id)
    if timeline is None:
        plan = store.get_video_plan_for_script(script_id)
        structured = {
            "has_timeline": False,
            "has_video_plan": plan is not None,
            "shot_count": len(plan.shots) if plan else 0,
            "message": "尚无剪辑时间轴" if not plan else "有分镜计划但未生成剪辑时间轴",
        }
    else:
        board = timeline_board_items(store, timeline)
        layer_summary = build_timeline_layer_summary(store, timeline)
        layers_info = []
        for layer in timeline.video_layers:
            layers_info.append(
                {
                    "id": layer.id,
                    "name": layer.name,
                    "z_index": layer.z_index,
                    "clip_count": len(layer.clips),
                    "clips": [
                        {
                            "id": c.id,
                            "start_ms": c.start_ms,
                            "end_ms": c.end_ms,
                            "label": c.label,
                            "asset_ref": c.asset_ref,
                            "transform": c.transform,
                        }
                        for c in layer.clips
                    ],
                }
            )
        structured = {
            "has_timeline": True,
            "duration_ms": board.get("duration_ms", timeline_duration_ms(timeline)),
            "revision": timeline.revision,
            "video_layers": layers_info,
            "audio_clips": len(board.get("tracks", {}).get("audio", [])),
            "subtitle_clips": len(board.get("tracks", {}).get("subtitle", [])),
            "layer_summary": layer_summary,
        }

    obs = json.dumps(structured, ensure_ascii=False, indent=2)
    return ToolResult(observation=obs, structured=structured)


def handle_add_clip(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """添加媒体片段到时间轴。"""
    script_id = _script_from_ctx(ctx)
    project_id = _project_from_ctx(ctx)
    media_id = str(args.get("media_id", ""))
    track = str(args.get("track", "video"))
    start_ms = int(args.get("start_ms", 0))
    layer_id = str(args.get("layer_id", ""))
    label = str(args.get("label", ""))

    # 查找媒体资产信息
    media = store.media_assets.get(media_id)
    if not media:
        return ToolResult(
            observation=f"媒体资产 {media_id} 不存在",
            structured={"error": f"media {media_id} not found"},
            ok=False,
        )

    try:
        duration_ms = int(args.get("duration_ms") or 0)
    except (TypeError, ValueError):
        duration_ms = 0
    if duration_ms <= 0:
        duration_ms = _resolve_media_default_duration_ms(store, media)

    if not label:
        label = media.name or media_id

    access = resolve_media_access(media.url)
    preview_url = access.get("link", media.url)

    timeline = store.get_edit_timeline_for_script(script_id)
    if timeline is None:
        return ToolResult(
            observation="尚无剪辑时间轴，请先通过 editing_agent 的 plan_edit_timeline 生成",
            structured={"error": "no timeline"},
            ok=False,
        )

    # 构建新 clip
    import time

    new_clip: dict[str, Any] = {
        "id": f"agent_clip_{int(time.time() * 1000)}",
        "start_ms": start_ms,
        "end_ms": start_ms + duration_ms,
        "label": label,
        "asset_ref": media_id,
        "preview_url": preview_url,
        "preview_media_type": media.type.value,
        "transform": {"x": 0.5, "y": 0.5, "width": 1, "height": 1, "opacity": 1, "rotation": 0, "keyframes": []},
        "metadata": {"edited_by": "agent", "media_id": media_id},
    }

    # 更新对应层/轨：video 追加到指定层，audio/subtitle 追加到现有轨（禁止整轨替换）
    if track == "video":
        body: dict[str, Any] = {"video_layers": []}
        found_layer = False
        for layer in timeline.video_layers:
            layer_dict = {
                "id": layer.id,
                "name": layer.name,
                "z_index": layer.z_index,
                "clips": [_clip_to_raw(c) for c in layer.clips],
            }
            if layer_id and layer.id == layer_id:
                layer_dict["clips"].append(new_clip)
                found_layer = True
            body["video_layers"].append(layer_dict)

        if not found_layer:
            if body["video_layers"]:
                # 添加到第一个视频层
                body["video_layers"][0]["clips"].append(new_clip)
            else:
                body["video_layers"] = [
                    {"id": "", "name": "主画面", "z_index": 0, "clips": [new_clip]}
                ]
    else:
        track_key = track if track in ("audio", "subtitle") else "audio"
        tracks_body = {
            key: [_clip_to_raw(c) for c in timeline.tracks.get(key, [])]
            for key in ("audio", "subtitle")
        }
        tracks_body[track_key].append(new_clip)
        body = {"tracks": tracks_body}

    try:
        view = patch_timeline(store, script_id=script_id, project_id=project_id, body=body)
        schedule_save(store, immediate=True)
        ctx.outputs.append(
            StepOutput(kind="json", label=f"add_clip:{track}", asset_id=media_id)
        )
        return ToolResult(
            observation=f"已在 {track} 轨添加片段「{label}」({new_clip['id']})，位置 {start_ms}ms，时长 {duration_ms}ms",
            structured={"action": "add_clip", "clip_id": new_clip["id"], "track": track, "revision": view.get("revision")},
        )
    except Exception as e:
        return ToolResult(observation=f"添加片段失败：{e}", structured={"error": str(e)}, ok=False)


def handle_update_clip(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """修改片段属性。"""
    script_id = _script_from_ctx(ctx)
    project_id = _project_from_ctx(ctx)
    clip_id = str(args.get("clip_id", ""))

    timeline = store.get_edit_timeline_for_script(script_id)
    if timeline is None:
        return ToolResult(observation="尚无剪辑时间轴", ok=False)

    # 查找并更新 clip
    patched = False
    body: dict[str, Any] = {"video_layers": []}
    for layer in timeline.video_layers:
        layer_dict = {
            "id": layer.id,
            "name": layer.name,
            "z_index": layer.z_index,
            "clips": [],
        }
        for c in layer.clips:
            clip_dict = _clip_to_raw(c)
            if c.id == clip_id:
                patched = True
                if "start_ms" in args:
                    clip_dict["start_ms"] = int(args["start_ms"])
                if "end_ms" in args:
                    clip_dict["end_ms"] = int(args["end_ms"])
                if "label" in args:
                    clip_dict["label"] = str(args["label"])
                if "transform" in args and isinstance(args["transform"], dict):
                    existing = dict(clip_dict.get("transform") or {})
                    existing.update(args["transform"])
                    clip_dict["transform"] = existing
                if "motion" in args:
                    clip_dict["motion"] = str(args["motion"])
                if "transition_in" in args:
                    clip_dict["transition_in"] = args["transition_in"]
                if "transition_out" in args:
                    clip_dict["transition_out"] = args["transition_out"]
            layer_dict["clips"].append(clip_dict)
        body["video_layers"].append(layer_dict)

    if not patched:
        return ToolResult(observation=f"未找到片段 {clip_id}", ok=False)

    try:
        view = patch_timeline(store, script_id=script_id, project_id=project_id, body=body)
        schedule_save(store, immediate=True)
        return ToolResult(
            observation=f"已更新片段 {clip_id}",
            structured={"action": "update_clip", "clip_id": clip_id, "revision": view.get("revision")},
        )
    except Exception as e:
        return ToolResult(observation=f"更新片段失败：{e}", ok=False)


def handle_remove_clip(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """删除片段。"""
    script_id = _script_from_ctx(ctx)
    project_id = _project_from_ctx(ctx)
    clip_id = str(args.get("clip_id", ""))

    timeline = store.get_edit_timeline_for_script(script_id)
    if timeline is None:
        return ToolResult(observation="尚无剪辑时间轴", ok=False)

    removed = False
    body: dict[str, Any] = {"video_layers": []}
    for layer in timeline.video_layers:
        layer_dict = {
            "id": layer.id,
            "name": layer.name,
            "z_index": layer.z_index,
            "clips": [],
        }
        for c in layer.clips:
            if c.id == clip_id:
                removed = True
                continue
            layer_dict["clips"].append(_clip_to_raw(c))
        body["video_layers"].append(layer_dict)

    if not removed:
        return ToolResult(observation=f"未找到片段 {clip_id}", ok=False)

    try:
        view = patch_timeline(store, script_id=script_id, project_id=project_id, body=body)
        schedule_save(store, immediate=True)
        return ToolResult(
            observation=f"已删除片段 {clip_id}",
            structured={"action": "remove_clip", "clip_id": clip_id},
        )
    except Exception as e:
        return ToolResult(observation=f"删除片段失败：{e}", ok=False)


def handle_apply_effect(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """应用视觉效果并持久化到时间轴。"""
    script_id = _script_from_ctx(ctx)
    project_id = _project_from_ctx(ctx)
    clip_id = str(args.get("clip_id", ""))
    effect_type = str(args.get("effect_type", ""))
    params = args.get("params") or {}

    timeline = store.get_edit_timeline_for_script(script_id)
    if timeline is None:
        return ToolResult(observation="尚无剪辑时间轴", ok=False)

    patched = False
    body: dict[str, Any] = {"video_layers": []}
    for layer in timeline.video_layers:
        layer_dict = {
            "id": layer.id,
            "name": layer.name,
            "z_index": layer.z_index,
            "clips": [],
        }
        for c in layer.clips:
            clip_dict = _clip_to_raw(c)
            if c.id == clip_id:
                patched = True
                meta = dict(clip_dict.get("metadata") or {})
                meta["effect_type"] = effect_type
                meta["effect_params"] = params
                clip_dict["metadata"] = meta
            layer_dict["clips"].append(clip_dict)
        body["video_layers"].append(layer_dict)

    if not patched:
        return ToolResult(observation=f"未找到片段 {clip_id}", ok=False)

    try:
        view = patch_timeline(store, script_id=script_id, project_id=project_id, body=body)
        schedule_save(store, immediate=True)
        return ToolResult(
            observation=f"特效「{effect_type}」已应用于片段 {clip_id}",
            structured={
                "action": "apply_effect",
                "clip_id": clip_id,
                "effect_type": effect_type,
                "params": params,
                "revision": view.get("revision"),
            },
        )
    except Exception as e:
        return ToolResult(observation=f"应用特效失败：{e}", ok=False)


def handle_set_keyframe(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """设置动画关键帧并持久化到时间轴。"""
    script_id = _script_from_ctx(ctx)
    project_id = _project_from_ctx(ctx)
    clip_id = str(args.get("clip_id", ""))
    time_ms = int(args.get("time_ms", 0))
    props = args.get("properties") or {}

    timeline = store.get_edit_timeline_for_script(script_id)
    if timeline is None:
        return ToolResult(observation="尚无剪辑时间轴", ok=False)

    patched = False
    body: dict[str, Any] = {"video_layers": []}
    for layer in timeline.video_layers:
        layer_dict = {
            "id": layer.id,
            "name": layer.name,
            "z_index": layer.z_index,
            "clips": [],
        }
        for c in layer.clips:
            clip_dict = _clip_to_raw(c)
            if c.id == clip_id:
                patched = True
                transform = dict(clip_dict.get("transform") or {})
                keyframes = list(transform.get("keyframes") or [])
                keyframes.append({"time_ms": time_ms, **props})
                transform["keyframes"] = keyframes
                clip_dict["transform"] = transform
            layer_dict["clips"].append(clip_dict)
        body["video_layers"].append(layer_dict)

    if not patched:
        return ToolResult(observation=f"未找到片段 {clip_id}", ok=False)

    try:
        view = patch_timeline(store, script_id=script_id, project_id=project_id, body=body)
        schedule_save(store, immediate=True)
        return ToolResult(
            observation=f"已在片段 {clip_id} 的 {time_ms}ms 处设置关键帧",
            structured={
                "action": "set_keyframe",
                "clip_id": clip_id,
                "time_ms": time_ms,
                "properties": props,
                "revision": view.get("revision"),
            },
        )
    except Exception as e:
        return ToolResult(observation=f"设置关键帧失败：{e}", ok=False)


def handle_export_timeline(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """触发视频导出。"""
    from core.edit.export_settings import CLASSIC_EXPORT_ONLY_MESSAGE, get_export_manager

    if not get_export_manager().is_ffmpeg_export_enabled():
        return ToolResult(observation=CLASSIC_EXPORT_ONLY_MESSAGE, ok=False)

    script_id = _script_from_ctx(ctx)
    project_id = _project_from_ctx(ctx)
    skip_subtitles = bool(args.get("skip_subtitles"))

    timeline = store.get_edit_timeline_for_script(script_id)
    if timeline is None:
        return ToolResult(observation="尚无剪辑时间轴，无法导出", ok=False)

    from core.edit.export_jobs import create_export_job, run_export_job
    from core.edit.export_paths import export_filename_for_asset, prepare_export_output_path
    from core.edit.ffmpeg_renderer import export_timeline_to_mp4
    from core.edit.export_settings import get_export_manager
    from core.models.entities import AssetStatus, MediaAsset, MediaAssetType, VideoStyleMode, new_id

    job = create_export_job(project_id, script_id)
    job_id = job.id

    script = store.get_script(script_id)
    style_mode = script.style_mode if script else VideoStyleMode.STORYBOOK

    import threading

    def worker(_job):
        fin_id = new_id("media")
        out_path = prepare_export_output_path(project_id, script_id, fin_id)
        result = export_timeline_to_mp4(
            store, timeline, out_path,
            project_id=project_id, script_id=script_id,
            style_mode=style_mode, manager=get_export_manager(),
            skip_subtitles=skip_subtitles,
        )
        export_name = export_filename_for_asset(fin_id)
        url = f"/api/projects/{project_id}/scripts/{script_id}/exports/{export_name}"
        media = MediaAsset(
            id=fin_id, project_id=project_id, script_id=script_id,
            type=MediaAssetType.FINAL, name="final_video", url=url,
            status=AssetStatus.GENERATED,
            metadata={"render": "ffmpeg", "duration_ms": result.duration_ms, "segment_count": result.segment_count},
        )
        store.add_media_asset(media)
        schedule_save(store, immediate=True)
        return {"asset_id": fin_id, "url": url, "duration_ms": result.duration_ms}

    threading.Thread(target=lambda: run_export_job(job_id, worker), daemon=True).start()

    return ToolResult(
        observation=f"导出任务已提交，job_id={job_id}，可通过 get_export_status 查询进度",
        structured={"action": "export_timeline", "job_id": job_id},
    )


def handle_get_export_status(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    """查询导出进度。"""
    from core.edit.export_jobs import get_export_job, job_to_dict

    job_id = str(args.get("job_id", ""))
    job = get_export_job(job_id)
    if job is None:
        return ToolResult(observation=f"导出任务 {job_id} 不存在", ok=False)

    info = job_to_dict(job)
    obs = json.dumps(info, ensure_ascii=False, indent=2)
    return ToolResult(observation=obs, structured=info)


# Handler 注册表
OPEN_CUT_HANDLERS: dict[str, Any] = {
    "get_edit_timeline": handle_get_edit_timeline,
    "add_clip": handle_add_clip,
    "update_clip": handle_update_clip,
    "remove_clip": handle_remove_clip,
    "apply_effect": handle_apply_effect,
    "set_keyframe": handle_set_keyframe,
    "export_timeline": handle_export_timeline,
    "get_export_status": handle_get_export_status,
}
