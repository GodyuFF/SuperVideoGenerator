"""主编排 pipeline 进度推断与用户续跑意图。"""

from __future__ import annotations

import re
from typing import Any

from core.edit.timeline import build_tts_by_shot, resolve_shot_image_ref
from core.llm.master.actions import pipeline_for_style, uses_image_text_pipeline
from core.llm.tools.image.scan import build_scan_text_assets_payload
from core.llm.tools.shared.media_list import resolve_media_access
from core.models.entities import MediaAssetType, TextAssetType, VideoStyleMode
from core.store.memory import MemoryStore

_IMAGE_TEXT_VISUAL = frozenset(
    {
        TextAssetType.CHARACTER.value,
        TextAssetType.SCENE.value,
        TextAssetType.PROP.value,
    }
)

_UPSTREAM_FOR_EDIT = ("script_design", "image_gen", "storyboard", "tts_gen")

_RESUME_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"剪辑|合成|成片|edit_compose|compose", re.I), "edit_compose"),
    (re.compile(r"配音|旁白|tts|语音", re.I), "tts_gen"),
    (re.compile(r"分镜|storyboard|镜头计划", re.I), "storyboard"),
    (re.compile(r"生图|配图|image_gen", re.I), "image_gen"),
    (re.compile(r"剧本设计|从剧本|继续剧本|写剧本|script_design", re.I), "script_design"),
    (re.compile(r"视频生成|video_gen|ai\s*视频", re.I), "video_gen"),
]


def detect_resume_target_step(user_message: str) -> str | None:
    """识别用户是否明确要求从某 pipeline 步骤继续。"""
    text = (user_message or "").strip()
    if not text:
        return None
    for pattern, step_type in _RESUME_PATTERNS:
        if pattern.search(text):
            return step_type
    return None


def _has_script_design(store: MemoryStore, script_id: str) -> bool:
    script = store.get_script(script_id)
    if script and (script.content_md or "").strip():
        return True
    for asset in store.list_assets_for_script(script_id):
        if asset.type.value in (
            "plot",
            "narration",
            TextAssetType.CHARACTER.value,
            TextAssetType.SCENE.value,
            TextAssetType.PROP.value,
        ):
            return True
    return False


def _image_gen_complete(store: MemoryStore, script_id: str) -> bool:
    try:
        scan = build_scan_text_assets_payload(store, script_id)
    except ValueError:
        return False
    assets = scan.get("assets") or []
    visual = [a for a in assets if a.get("type") in _IMAGE_TEXT_VISUAL]
    if not visual:
        return True
    pending = int(scan.get("pending_count", 0))
    if pending > 0:
        return False
    return any(a.get("has_image") and a.get("image_status") == "ready" for a in visual)


def _storyboard_complete(store: MemoryStore, script_id: str) -> bool:
    plan = store.get_video_plan_for_script(script_id)
    return plan is not None and len(plan.shots) > 0


def _tts_complete(store: MemoryStore, script_id: str) -> bool:
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return False
    tts_by_shot = build_tts_by_shot(store, script_id)
    for shot in plan.shots:
        narration = (shot.narration_text or "").strip()
        if not narration:
            continue
        audio_id = tts_by_shot.get(shot.id)
        if not audio_id:
            return False
        media = store.media_assets.get(audio_id)
        if not media or media.type != MediaAssetType.AUDIO:
            return False
        if not resolve_media_access(media.url).get("is_accessible"):
            return False
    return True


def _video_gen_complete(store: MemoryStore, script_id: str) -> bool:
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return False
    videos = [
        m
        for m in store.list_media_for_script(script_id)
        if m.type == MediaAssetType.VIDEO
        and resolve_media_access(m.url).get("is_accessible")
    ]
    return len(videos) >= len(plan.shots)


def _edit_compose_complete(store: MemoryStore, script_id: str) -> bool:
    if store.get_edit_timeline_for_script(script_id) is not None:
        return True
    finals = [
        m
        for m in store.list_media_for_script(script_id)
        if m.type == MediaAssetType.FINAL
        and resolve_media_access(m.url).get("is_accessible")
    ]
    return bool(finals)


def _edit_compose_gaps(store: MemoryStore, script_id: str) -> list[str]:
    gaps: list[str] = []
    if not _storyboard_complete(store, script_id):
        gaps.append("缺少 VideoPlan 分镜（storyboard）")
        return gaps
    plan = store.get_video_plan_for_script(script_id)
    assert plan is not None
    if uses_image_text_pipeline(plan.mode):
        if not _image_gen_complete(store, script_id):
            gaps.append("配图未齐备（image_gen）")
        tts_by_shot = build_tts_by_shot(store, script_id)
        for shot in plan.shots:
            if (shot.narration_text or "").strip() and shot.id not in tts_by_shot:
                gaps.append(f"镜头 {shot.order + 1} 缺配音（tts_gen）")
            image_id = resolve_shot_image_ref(store, shot)
            if not image_id:
                gaps.append(f"镜头 {shot.order + 1} 缺可访问图片（image_gen）")
    else:
        if not _video_gen_complete(store, script_id):
            gaps.append("AI 视频片段未齐备（video_gen）")
    return gaps


def infer_completed_step_types(
    store: MemoryStore,
    script_id: str,
    style_mode: VideoStyleMode,
) -> set[str]:
    """根据 Store 快照推断可视为已完成的 step_type。"""
    completed: set[str] = set()
    if _has_script_design(store, script_id):
        completed.add("script_design")
    if uses_image_text_pipeline(style_mode):
        if _image_gen_complete(store, script_id):
            completed.add("image_gen")
    if _storyboard_complete(store, script_id):
        completed.add("storyboard")
    if _tts_complete(store, script_id):
        completed.add("tts_gen")
    if style_mode == VideoStyleMode.AI_VIDEO and _video_gen_complete(store, script_id):
        completed.add("video_gen")
    if _edit_compose_complete(store, script_id):
        completed.add("edit_compose")
    return completed


def build_pipeline_progress(
    store: MemoryStore,
    script_id: str,
    style_mode: VideoStyleMode,
) -> dict[str, Any]:
    """主编排状态 JSON 用的 pipeline 进度摘要。"""
    inferred = sorted(infer_completed_step_types(store, script_id, style_mode))
    gaps = _edit_compose_gaps(store, script_id)
    ready = len(gaps) == 0 and _storyboard_complete(store, script_id)
    if style_mode == VideoStyleMode.AI_VIDEO:
        ready = ready and _video_gen_complete(store, script_id)
    elif uses_image_text_pipeline(style_mode):
        ready = ready and _image_gen_complete(store, script_id) and _tts_complete(
            store, script_id
        )
    pipeline = pipeline_for_style(style_mode)
    return {
        "inferred_completed_steps": inferred,
        "ready_for_edit_compose": ready,
        "gaps": gaps,
        "pipeline": pipeline,
    }


def upstream_steps_for_edit(style_mode: VideoStyleMode) -> tuple[str, ...]:
    """剪辑合成前通常需完成的上游步骤。"""
    if style_mode == VideoStyleMode.AI_VIDEO:
        return ("script_design", "storyboard", "video_gen", "tts_gen")
    return _UPSTREAM_FOR_EDIT


def build_resume_observation(
    *,
    resume_target: str | None,
    progress: dict[str, Any],
    user_message: str,
) -> str | None:
    """根据续跑意图与进度生成首条主编排 observation。"""
    if not resume_target:
        return None
    gaps = progress.get("gaps") or []
    ready = bool(progress.get("ready_for_edit_compose"))
    inferred = progress.get("inferred_completed_steps") or []

    if resume_target == "edit_compose":
        if ready:
            return (
                "用户要求从剪辑合成继续；Store 显示 VideoPlan、配图与配音已就绪，"
                "建议直接 delegate_edit_compose，勿重跑 delegate_script_design。"
            )
        gap_text = "；".join(gaps[:5]) if gaps else "上游素材未齐备"
        return (
            f"用户要求从剪辑合成继续，但仍有缺口：{gap_text}。"
            "建议先 tool_list_assets 核对，再仅委派缺失的上游步骤，勿全量重跑剧本。"
        )

    if resume_target in inferred:
        delegate = f"delegate_{resume_target}"
        return (
            f"用户要求从「{resume_target}」继续；Store 显示该步素材已存在（见 inferred_completed_steps），"
            f"本对话可重新委派 {delegate} 或继续下游；请结合 user_message 决定。"
        )

    return (
        f"用户消息指向步骤「{resume_target}」；当前已推断完成：{', '.join(inferred) or '无'}。"
        f"请结合 pipeline_progress 与 tool_list_assets 决定下一步。"
    )
