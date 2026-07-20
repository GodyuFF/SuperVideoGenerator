"""主编排 pipeline 进度推断与用户续跑意图。"""

from __future__ import annotations

import re
from typing import Any

from core.edit.shot_detail_sync import is_shot_detail_complete
from core.edit.timeline import (
    build_tts_by_shot,
    resolve_shot_image_ref,
    resolve_shot_video_ref,
)
from core.llm.master.actions import (
    uses_ai_video_pipeline,
    uses_frame_i2v_pipeline,
    uses_image_text_pipeline,
)
from core.llm.tools.image.scan import build_scan_text_assets_payload
from core.llm.tools.shared.media_list import resolve_media_access
from core.models.entities import MediaAssetType, TextAssetType, VideoStyleMode
from core.store.memory import MemoryStore

_IMAGE_TEXT_VISUAL = frozenset(
    {
        TextAssetType.CHARACTER.value,
        TextAssetType.SCENE.value,
        TextAssetType.PROP.value,
        TextAssetType.FRAME.value,
    }
)

_UPSTREAM_FOR_EDIT = ("script_design", "storyboard", "image_gen", "tts_gen", "shot_detail")

_RESUME_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"剪辑|合成|成片|edit_compose|compose", re.I), "edit_compose"),
    (re.compile(r"分镜详设|shot_detail|详设", re.I), "shot_detail"),
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
            TextAssetType.FRAME.value,
        ):
            return True
    return False


def _frames_cover_all_shots(store: MemoryStore, script_id: str) -> bool:
    """图文管线：VideoPlan 存在时，每子镜须关联 frame 剧本画面资产。"""
    from core.edit.sub_shot_helpers import sub_shot_has_frame_link

    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return True
    if not uses_image_text_pipeline(plan.mode):
        return True
    for shot in plan.shots:
        if not shot.sub_shots:
            return False
        for sub in shot.sub_shots:
            if not sub_shot_has_frame_link(sub):
                return False
    return True


def _shot_voice_text(shot) -> str:
    """拼接镜内 voice 音频 clip 文案。"""
    return "".join(
        c.text.strip()
        for t in shot.audio_tracks
        if t.kind == "voice"
        for c in t.clips
        if c.text.strip()
    )


def _image_gen_complete(store: MemoryStore, script_id: str) -> bool:
    """image_gen 完成判定：全部视觉资产（含每个 frame）均已有可用图。"""
    try:
        scan = build_scan_text_assets_payload(store, script_id)
    except ValueError:
        return False
    assets = scan.get("assets") or []
    visual = [a for a in assets if a.get("type") in _IMAGE_TEXT_VISUAL]
    if not visual:
        # 尚无角色/场景/道具/frame 时绝不能视为配图已完成（空剧本会误标 step:image_gen）
        return False
    pending = int(scan.get("pending_count", 0))
    if pending > 0:
        return False
    for asset in visual:
        if asset.get("has_image") and asset.get("image_status") == "ready":
            continue
        # frame 缺图一律视为未完成（含参考图未就绪场景），不再豁免
        return False
    return _frames_cover_all_shots(store, script_id)


def _storyboard_complete(store: MemoryStore, script_id: str) -> bool:
    plan = store.get_video_plan_for_script(script_id)
    return plan is not None and len(plan.shots) > 0


def _tts_complete(store: MemoryStore, script_id: str) -> bool:
    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return False
    require_voice = uses_image_text_pipeline(plan.mode)
    tts_by_shot = build_tts_by_shot(store, script_id)
    any_voice_required = False
    for shot in plan.shots:
        narration = _shot_voice_text(shot)
        if require_voice and shot.sub_shots and not narration:
            return False
        if not narration:
            continue
        any_voice_required = True
        audio_id = tts_by_shot.get(shot.id)
        if not audio_id:
            return False
        media = store.media_assets.get(audio_id)
        if not media or media.type != MediaAssetType.AUDIO:
            return False
        if not resolve_media_access(media.url).get("is_accessible"):
            return False
    if require_voice and not any_voice_required:
        return False
    return True


def _shot_detail_complete(store: MemoryStore, script_id: str) -> bool:
    """分镜详设完成：detail_revision > 0 且每镜 TTS 同步并有展示说明。"""
    return is_shot_detail_complete(store, script_id)


def _storyboard_review_gaps(
    store: MemoryStore,
    script_id: str,
    *,
    style_mode: VideoStyleMode | None = None,
) -> list[str]:
    """分镜复核前缺失项（复核为剪辑前最后一步）。"""
    gaps: list[str] = []
    if not _storyboard_complete(store, script_id):
        gaps.append("缺少 VideoPlan（storyboard）")
        return gaps
    if not _tts_complete(store, script_id):
        gaps.append("缺少 TTS 配音（tts_gen）")
    if not _image_gen_complete(store, script_id):
        gaps.append("缺少画面配图（image_gen）")
    mode = style_mode
    if mode is None:
        plan = store.get_video_plan_for_script(script_id)
        mode = plan.mode if plan is not None else None
    if uses_ai_video_pipeline(mode or "") and not _video_gen_complete(store, script_id):
        gaps.append("缺少 AI 视频片段（video_gen）；须先 video 再复核")
    return gaps


def _video_clips_cover_all_shots(store: MemoryStore, script_id: str) -> bool:
    """AI 视频管线：VideoPlan 存在时，每子镜须关联 video_clip 文字资产。"""
    from core.edit.sub_shot_helpers import sub_shot_has_video_clip_link

    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return True
    if not uses_ai_video_pipeline(plan.mode):
        return True
    for shot in plan.shots:
        if not shot.sub_shots:
            return False
        for sub in shot.sub_shots:
            if not sub_shot_has_video_clip_link(sub):
                return False
    return True


def _video_gen_complete(store: MemoryStore, script_id: str) -> bool:
    """AI 视频管线：每子镜须绑定 video_clip 且已生成可访问视频 media。"""
    from core.llm.tools.video.scan import scan_video_clips

    plan = store.get_video_plan_for_script(script_id)
    if not plan or not plan.shots:
        return False
    if not uses_ai_video_pipeline(plan.mode):
        return False
    if not _video_clips_cover_all_shots(store, script_id):
        return False
    try:
        scan = scan_video_clips(store, script_id)
    except ValueError:
        return False
    if int(scan.get("pending_count", 0)) > 0:
        return False
    for shot in plan.shots:
        media_id = resolve_shot_video_ref(store, shot)
        if not media_id:
            return False
        media = store.media_assets.get(media_id)
        if not media or media.type != MediaAssetType.VIDEO:
            return False
        if not resolve_media_access(media.url).get("is_accessible"):
            return False
    return True


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
    if uses_image_text_pipeline(plan.mode) and not uses_frame_i2v_pipeline(plan.mode):
        if not _image_gen_complete(store, script_id):
            gaps.append("配图未齐备（image_gen）")
        tts_by_shot = build_tts_by_shot(store, script_id)
        for shot in plan.shots:
            if _shot_voice_text(shot) and shot.id not in tts_by_shot:
                gaps.append(f"镜头 {shot.order + 1} 缺配音（tts_gen）")
            image_id = resolve_shot_image_ref(store, shot)
            if not image_id:
                gaps.append(f"镜头 {shot.order + 1} 缺可访问图片（image_gen）")
        if not _shot_detail_complete(store, script_id):
            gaps.append("分镜详设未完成（shot_detail）")
    elif uses_frame_i2v_pipeline(plan.mode):
        if not _image_gen_complete(store, script_id):
            gaps.append("配图未齐备（image_gen）")
        if not _video_gen_complete(store, script_id):
            gaps.append("AI 视频片段未齐备（video_gen）")
        tts_by_shot = build_tts_by_shot(store, script_id)
        for shot in plan.shots:
            if _shot_voice_text(shot) and shot.id not in tts_by_shot:
                gaps.append(f"镜头 {shot.order + 1} 缺配音（tts_gen）")
        if not _shot_detail_complete(store, script_id):
            gaps.append("分镜详设未完成（shot_detail）")
    else:
        if not _video_gen_complete(store, script_id):
            gaps.append("AI 视频片段未齐备（video_gen）")
        if not _shot_detail_complete(store, script_id):
            gaps.append("分镜详设未完成（shot_detail）")
    return gaps


_FULL_REDO_RE = re.compile(
    r"全部重做|全部重来|推倒重来|从头(再来|开始|制作)|重新制作整[部个]|从零(开始|再做)",
    re.I,
)

# 明确重做 / 从某步继续（避免「旁白」「分镜」等普通提及误伤复用）
_REOPEN_STEP_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"重新配音|重做配音|再合成配音|重新合成配音|重录(旁白|配音)", re.I), "tts_gen"),
    (re.compile(r"重新分镜|重做分镜|重写分镜|重做镜头", re.I), "storyboard"),
    (re.compile(r"重新生图|重做(配图|生图)|重新配图", re.I), "image_gen"),
    (re.compile(r"重新(写)?剧本|重做剧本|推倒剧本", re.I), "script_design"),
    (re.compile(r"重新详设|重做详设|重跑详设", re.I), "shot_detail"),
    (re.compile(r"重新(生成)?视频|重做视频片段", re.I), "video_gen"),
    (
        re.compile(
            r"重新剪辑|重做剪辑|再剪一|从剪辑|继续(成片|剪辑|合成)|继续成片|从合成继续|重新合成成片",
            re.I,
        ),
        "edit_compose",
    ),
]

# 用户要求重做某步时，下游完成态一并作废，避免沿用过期配音/详设/成片
_DOWNSTREAM_INVALIDATE: dict[str, tuple[str, ...]] = {
    "script_design": (
        "storyboard",
        "image_gen",
        "tts_gen",
        "shot_detail",
        "video_gen",
        "edit_compose",
    ),
    "storyboard": ("tts_gen", "shot_detail", "video_gen", "edit_compose"),
    "image_gen": ("shot_detail", "edit_compose"),
    "tts_gen": ("shot_detail", "edit_compose"),
    "video_gen": ("shot_detail", "edit_compose"),
    "shot_detail": ("edit_compose",),
    "edit_compose": (),
}


def detect_reopen_steps(user_message: str) -> set[str]:
    """识别用户明确要求重做或从某步继续的步骤集合。"""
    text = (user_message or "").strip()
    if not text:
        return set()
    found: set[str] = set()
    for pattern, step_type in _REOPEN_STEP_PATTERNS:
        if pattern.search(text):
            found.add(step_type)
    return found


def seed_completed_steps_for_message(
    store: MemoryStore,
    script_id: str,
    style_mode: VideoStyleMode,
    user_message: str,
) -> set[str]:
    """
    新对话启动时根据 Store 复用已完成步骤。

    - 默认：inferred_completed_steps 全部记入 completed，避免无意义全量重跑。
    - 用户明确「全部重做」：不复用。
    - 用户明确重做/从某步继续：该步及下游不记入 completed。
    """
    text = (user_message or "").strip()
    if _FULL_REDO_RE.search(text):
        return set()
    completed = set(infer_completed_step_types(store, script_id, style_mode))
    for resume in detect_reopen_steps(text):
        completed.discard(resume)
        for dep in _DOWNSTREAM_INVALIDATE.get(resume, ()):
            completed.discard(dep)
    return completed


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
    if _shot_detail_complete(store, script_id):
        completed.add("shot_detail")
    if uses_ai_video_pipeline(style_mode) and _video_gen_complete(store, script_id):
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
    if uses_ai_video_pipeline(style_mode) and not uses_frame_i2v_pipeline(style_mode):
        ready = ready and _video_gen_complete(store, script_id) and _shot_detail_complete(
            store, script_id
        )
    elif uses_frame_i2v_pipeline(style_mode):
        ready = (
            ready
            and _image_gen_complete(store, script_id)
            and _video_gen_complete(store, script_id)
            and _tts_complete(store, script_id)
            and _shot_detail_complete(store, script_id)
        )
    elif uses_image_text_pipeline(style_mode):
        ready = (
            ready
            and _image_gen_complete(store, script_id)
            and _tts_complete(store, script_id)
            and _shot_detail_complete(store, script_id)
        )
    from core.llm.master.delegate_deps import (
        delegates_for_style,
        eligible_delegates,
        resolve_delegate_readiness,
    )

    delegates = delegates_for_style(style_mode)
    readiness = resolve_delegate_readiness(store, script_id, style_mode)
    eligible = eligible_delegates(store, script_id, style_mode)
    return {
        "inferred_completed_steps": inferred,
        "ready_for_edit_compose": ready,
        "gaps": gaps,
        "eligible_delegates": eligible,
        "delegate_readiness": readiness,
        "delegates_for_style": delegates,
    }


def upstream_steps_for_edit(style_mode: VideoStyleMode) -> tuple[str, ...]:
    """剪辑合成前通常需完成的上游步骤。"""
    if uses_frame_i2v_pipeline(style_mode):
        return ("script_design", "storyboard", "image_gen", "video_gen", "tts_gen", "shot_detail")
    if uses_ai_video_pipeline(style_mode):
        return ("script_design", "storyboard", "video_gen", "tts_gen", "shot_detail")
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
                "建议直接 delegate_agent(agent_id=editing_agent)，勿重跑 script_agent。"
            )
        gap_text = "；".join(gaps[:5]) if gaps else "上游素材未齐备"
        return (
            f"用户要求从剪辑合成继续，但仍有缺口：{gap_text}。"
            "建议先 tool_list_assets 核对，再仅委派缺失的上游步骤，勿全量重跑剧本。"
        )

    if resume_target in inferred:
        from core.llm.master.actions import STEP_META

        delegate_hint = STEP_META.get(resume_target, {}).get("agent", resume_target)
        return (
            f"用户要求从「{resume_target}」继续；Store 显示该步素材已存在（见 inferred_completed_steps），"
            f"本对话可重新委派 agent_id={delegate_hint} 或继续下游；请结合 user_message 决定。"
        )

    return (
        f"用户消息指向步骤「{resume_target}」；当前已推断完成：{', '.join(inferred) or '无'}。"
        f"请结合 pipeline_progress 与 tool_list_assets 决定下一步。"
    )
