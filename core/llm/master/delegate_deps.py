"""主编排 delegate 依赖与就绪状态（动态选步，非固定 pipeline 顺序）。"""

from __future__ import annotations

from typing import Any

from core.llm.master.delegate_tool import (
    DELEGATE_AGENT_ACTION,
    build_delegate_agent_candidates,
    steps_for_style,
)
from core.llm.master.pipeline_progress import (
    _has_script_design,
    _image_gen_complete,
    _shot_detail_complete,
    _storyboard_complete,
    _tts_complete,
)
from core.llm.tools.image.scan import build_scan_text_assets_payload
from core.llm.style.style_mode_registry import StyleModeRegistry
from core.models.entities import TextAssetType, VideoStyleMode
from core.store.memory import MemoryStore

# step_type → 建议先完成的软依赖（不满足时仍可出现，但 blockers 非空）
# shot_detail 为剪辑前最后一步；ai_video 下另须 video_gen（见 _resolve_blockers）
DELEGATE_SOFT_DEPS: dict[str, tuple[str, ...]] = {
    "storyboard": ("script_design",),
    "image_gen": ("script_design",),
    "video_gen": ("storyboard",),
    "tts_gen": ("storyboard",),
    "shot_detail": ("storyboard", "tts_gen", "image_gen"),
    "edit_compose": ("storyboard", "shot_detail"),
}

_IMAGE_VISUAL_TYPES = frozenset(
    {
        TextAssetType.CHARACTER.value,
        TextAssetType.SCENE.value,
        TextAssetType.PROP.value,
        TextAssetType.FRAME.value,
    }
)


def delegates_for_style(
    style_mode: VideoStyleMode | str,
    *,
    config: Any | None = None,
) -> list[str]:
    """该风格下主编排可出现的委派行动（统一为 delegate_agent）。"""
    if steps_for_style(style_mode, config=config):
        return [DELEGATE_AGENT_ACTION]
    return []


def _has_pending_image_work(store: MemoryStore, script_id: str) -> bool:
    """是否存在待生图文字资产（entity 或 frame）。"""
    try:
        scan = build_scan_text_assets_payload(store, script_id)
    except ValueError:
        return False
    assets = scan.get("assets") or []
    visual = [a for a in assets if a.get("type") in _IMAGE_VISUAL_TYPES]
    if not visual:
        return False
    pending = int(scan.get("pending_count", 0))
    if pending > 0:
        return True
    for asset in visual:
        if asset.get("needs_generation"):
            return True
    return False


def _image_gen_complete_for_review(store: MemoryStore, script_id: str) -> bool:
    """复核前 frame 配图须就绪。"""
    return _image_gen_complete(store, script_id)


def _resolve_blockers(
    store: MemoryStore,
    script_id: str,
    style_mode: VideoStyleMode,
    step_type: str,
) -> tuple[list[str], list[str]]:
    """返回 (soft_blockers, hard_blockers) 中文说明列表。"""
    soft: list[str] = []
    hard: list[str] = []

    if step_type == "video_gen" and not StyleModeRegistry.style_includes_video_gen(
        style_mode.value if isinstance(style_mode, VideoStyleMode) else str(style_mode)
    ):
        hard.append("当前风格不可委派 video_gen")

    if step_type == "image_gen":
        if not _has_script_design(store, script_id):
            soft.append("建议先完成剧本与文字资产（script_design）")
        elif not _has_pending_image_work(store, script_id):
            soft.append("当前无待生图文字资产；可先 storyboard 创建 frame 或补充角色/场景")

    if step_type == "storyboard" and not _has_script_design(store, script_id):
        soft.append("缺少剧本或文字资产（script_design）")

    if step_type == "tts_gen" and not _storyboard_complete(store, script_id):
        soft.append("缺少 VideoPlan（storyboard）")

    if step_type == "video_gen" and StyleModeRegistry.style_includes_video_gen(
        style_mode.value if isinstance(style_mode, VideoStyleMode) else str(style_mode)
    ):
        if not _storyboard_complete(store, script_id):
            soft.append("缺少 VideoPlan（storyboard）")

    if step_type == "shot_detail":
        if not _storyboard_complete(store, script_id):
            soft.append("缺少 VideoPlan（storyboard）")
        else:
            if not _tts_complete(store, script_id):
                soft.append("缺少 TTS 配音（tts_gen）")
            if not _image_gen_complete_for_review(store, script_id):
                soft.append("缺少画面配图（image_gen）")
            if StyleModeRegistry.style_includes_video_gen(
                style_mode.value if isinstance(style_mode, VideoStyleMode) else str(style_mode)
            ):
                from core.llm.master.pipeline_progress import _video_gen_complete

                if not _video_gen_complete(store, script_id):
                    soft.append("缺少 AI 视频片段（video_gen）；须先 video_agent 再分镜复核")

    if step_type == "edit_compose":
        from core.llm.master.pipeline_progress import _edit_compose_gaps

        gaps = _edit_compose_gaps(store, script_id)
        if gaps:
            soft.extend(gaps[:5])
        if not _shot_detail_complete(store, script_id):
            msg = "分镜详设未完成（shot_detail）；复核须为剪辑前最后一步"
            if msg not in soft and not any("shot_detail" in g for g in soft):
                soft.append(msg)

    return soft, hard


def resolve_delegate_readiness(
    store: MemoryStore,
    script_id: str,
    style_mode: VideoStyleMode,
    *,
    profile_id: str = "default",
    config: Any | None = None,
) -> list[dict[str, Any]]:
    """解析各子 Agent 的就绪状态，供主编排动态选步。"""
    rows: list[dict[str, Any]] = []
    for item in build_delegate_agent_candidates(
        profile_id, style_mode, config=config
    ):
        soft, hard = _resolve_blockers(
            store, script_id, style_mode, item.step_type
        )
        ready = not hard and not soft
        rows.append(
            {
                "agent_id": item.agent_id,
                "step_type": item.step_type,
                "ready": ready,
                "soft_blockers": soft,
                "hard_blockers": hard,
            }
        )
    return rows


def eligible_delegate_agent_ids(
    store: MemoryStore,
    script_id: str,
    style_mode: VideoStyleMode,
    *,
    profile_id: str = "default",
    config: Any | None = None,
    completed_step_types: set[str] | None = None,
) -> list[str]:
    """未完成且无硬拦的 agent_id 列表。"""
    completed = completed_step_types or set()
    out: list[str] = []
    for row in resolve_delegate_readiness(
        store, script_id, style_mode, profile_id=profile_id, config=config
    ):
        step_type = row.get("step_type") or ""
        if step_type in completed:
            continue
        if row.get("hard_blockers"):
            continue
        agent_id = row.get("agent_id")
        if agent_id:
            out.append(str(agent_id))
    return out


def eligible_delegates(
    store: MemoryStore,
    script_id: str,
    style_mode: VideoStyleMode,
    *,
    profile_id: str = "default",
    config: Any | None = None,
    completed_step_types: set[str] | None = None,
) -> list[str]:
    """未完成且无硬拦时返回 delegate_agent，否则空列表。"""
    ids = eligible_delegate_agent_ids(
        store,
        script_id,
        style_mode,
        profile_id=profile_id,
        config=config,
        completed_step_types=completed_step_types,
    )
    return [DELEGATE_AGENT_ACTION] if ids else []


def sort_next_delegate_agent_ids(
    agent_ids: list[str],
    readiness: list[dict[str, Any]],
) -> list[str]:
    """就绪 agent_id 优先，其余按 id 字母序。"""
    ready_set = {
        str(r["agent_id"])
        for r in readiness
        if r.get("ready") and r.get("agent_id")
    }
    ready = sorted(aid for aid in agent_ids if aid in ready_set)
    rest = sorted(aid for aid in agent_ids if aid not in ready_set)
    return ready + rest


def sort_next_delegates(
    delegates: list[str],
    readiness: list[dict[str, Any]],
) -> list[str]:
    """有未完成候选 agent 时返回 delegate_agent。"""
    pending_ids = [
        str(r["agent_id"])
        for r in readiness
        if r.get("agent_id") and not r.get("hard_blockers")
    ]
    if delegates and pending_ids:
        return [DELEGATE_AGENT_ACTION]
    return delegates


def is_hard_blocked(
    store: MemoryStore,
    script_id: str,
    style_mode: VideoStyleMode,
    agent_id: str,
    *,
    profile_id: str = "default",
    config: Any | None = None,
) -> str | None:
    """若指定 agent_id 被硬拦则返回原因，否则 None。"""
    from core.llm.agent.agent_registry import resolve_step_for_roster_agent

    step_type = resolve_step_for_roster_agent(
        agent_id, profile_id, config=config
    )
    if not step_type:
        return f"未知或不可委派的 agent_id: {agent_id}"
    _, hard = _resolve_blockers(store, script_id, style_mode, step_type)
    if hard:
        return hard[0]
    return None

