"""子 Agent 动作执行：通过 LLM 生成观察结果并落盘资产。"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from core.conversation import ConversationStore
from core.guards.script_title import apply_script_title_if_allowed
from core.llm.agent.asset_content import extract_llm_content_field, normalize_asset_content
from core.llm.agent.react_core import AgentRunContext
from core.llm.client import LLMClient
from core.llm.prompt.tools.registry import build_action_tool, tool_choice_force
from core.llm.client.settings import LLMConfigManager
from core.logging.perf import async_perf_span
from core.logging.setup import get_logger, log_stage
from core.llm.tools.shared.executor import AgentToolExecutor
from core.llm.agent.script_assets import (
    create_text_asset_for_action,
    delete_text_asset_for_action,
    update_text_asset_for_action,
)
from core.llm.prompt.config import ASSET_SUMMARY_MAX, IMAGE_PROMPT_SUMMARY_MAX, SCRIPT_MD_CONTEXT_MAX
from core.models.image_text_asset import (
    ensure_image_variants,
    find_variant,
    is_image_text_asset,
    normalize_image_text_content,
    update_variant_in_content,
)
from core.llm.prompt.builder import build_action_system, build_action_user, build_action_context_turn_content
from core.llm.prompt.chat_messages import (
    build_llm_request_ordered,
    messages_to_chat_history,
)
from core.llm.prompt.history_compress import prepare_react_chat_history
from core.llm.prompt.context_manager import AgentContextManager
from core.llm.prompt.registry import PromptProfile
from core.models.entities import (
    AssetReference,
    AssetScope,
    AssetStatus,
    MediaAsset,
    MediaAssetType,
    RelationType,
    Shot,
    ShotAudioClip,
    ShotAudioTrack,
    ShotSubtitle,
    ShotVideoClip,
    ShotVideoTrack,
    ShotSubShot,
    ShotSubShotImage,
    ShotSubShotVideo,
    StepOutput,
    TextAsset,
    TextAssetType,
    VideoPlan,
    VideoStyleMode,
    normalize_shot_orders,
    new_id,
)
from core.edit.sub_shot_helpers import (
    append_sub_shot_image,
    append_sub_shot_video,
    first_sub_shot_image,
    sub_shot_has_frame_link,
    sub_shot_has_video_clip_link,
)
from core.edit.sub_shot_produce import finalize_sub_shot
from core.store.memory import MemoryStore
from core.store.persist import schedule_save
from core.edit.timeline import flat_video_clips

logger = get_logger("core.agents.llm_action")

_SHOT_REF_KEYS = frozenset({"image", "character", "scene", "prop", "frame"})


def _ref_key_for_asset_id(store: MemoryStore, asset_id: str) -> str:
    ref_str = str(asset_id).strip()
    if not ref_str:
        return "image"
    media = store.media_assets.get(ref_str)
    if media and media.type == MediaAssetType.IMAGE:
        return "image"
    if ref_str.startswith("media_"):
        return "image"
    text = store.get_text_asset(ref_str)
    if text and text.type.value in _SHOT_REF_KEYS:
        return text.type.value
    if ref_str.startswith("char_"):
        return "character"
    if ref_str.startswith("scene_"):
        return "scene"
    if ref_str.startswith("prop_"):
        return "prop"
    if ref_str.startswith("frame_"):
        return "frame"
    return "image"


def normalize_shot_asset_refs(
    refs: Any,
    store: MemoryStore,
) -> dict[str, list[str]]:
    if not isinstance(refs, dict):
        return {}
    normalized: dict[str, list[str]] = {}
    for key, val in refs.items():
        ids = [str(v) for v in (val if isinstance(val, list) else [val]) if v]
        if not ids:
            continue
        if key == "asset_id":
            for ref_id in ids:
                bucket = _ref_key_for_asset_id(store, ref_id)
                normalized.setdefault(bucket, []).append(ref_id)
        elif str(key) in _SHOT_REF_KEYS:
            normalized.setdefault(str(key), []).extend(ids)
        else:
            for ref_id in ids:
                bucket = _ref_key_for_asset_id(store, ref_id)
                normalized.setdefault(bucket, []).append(ref_id)
    return normalized


def _normalize_shot_camera_motion(raw: Any) -> str:
    """将分镜运镜别名解析为 canonical preset。"""
    from core.edit.edit_capabilities import resolve_motion

    return resolve_motion(str(raw or "ken_burns_in"))


def _assert_sub_shots_have_frames(
    style_mode: Any,
    shots: list[Shot],
) -> None:
    """图文管线（故事书/漫画）persist_plan 前校验每子镜须有 frame 关联。"""
    from core.llm.master.actions import uses_image_text_pipeline

    if not shots or not uses_image_text_pipeline(style_mode):
        return
    missing: list[str] = []
    for shot in shots:
        if not shot.sub_shots:
            missing.append(f"镜{shot.order + 1}")
            continue
        for sub in shot.sub_shots:
            if not sub_shot_has_frame_link(sub):
                missing.append(f"镜{shot.order + 1}·子镜{sub.id[:8]}")
    if missing:
        labels = "、".join(missing[:8])
        suffix = f" 等{len(missing)}处" if len(missing) > 8 else ""
        raise ValueError(
            f"以下子镜缺少剧本画面 frame：{labels}{suffix}；"
            "请为每个子镜调用 create_frames（sub_shot_id 必填）后再 persist_plan"
        )


# 兼容测试导入旧名
_assert_shots_have_frames = _assert_sub_shots_have_frames


def _assert_sub_shots_have_video_clips(
    style_mode: Any,
    shots: list[Shot],
) -> None:
    """AI 视频管线 persist_plan 前校验每子镜须有 video_clip 关联。"""
    from core.llm.master.actions import uses_ai_video_pipeline

    if not shots or not uses_ai_video_pipeline(style_mode):
        return
    missing: list[str] = []
    for shot in shots:
        if not shot.sub_shots:
            missing.append(f"镜{shot.order + 1}")
            continue
        for sub in shot.sub_shots:
            if not sub_shot_has_video_clip_link(sub):
                missing.append(f"镜{shot.order + 1}·子镜{sub.id[:8]}")
    if missing:
        labels = "、".join(missing[:8])
        suffix = f" 等{len(missing)}处" if len(missing) > 8 else ""
        raise ValueError(
            f"以下子镜缺少 video_clip 文字资产：{labels}{suffix}；"
            "请为每个子镜调用 create_video_clips（sub_shot_id 必填）后再 persist_plan"
        )


def _assert_shots_have_voice_content(
    style_mode: Any,
    shots: list[Shot],
    *,
    store: MemoryStore | None = None,
    script_id: str = "",
) -> None:
    """图文管线 create_shots/persist_plan 前校验每镜须有 voice clip text 与合法说话人。"""
    from core.edit.shot_validate import validate_shots_voice_content, validate_shots_voice_speakers
    from core.llm.master.actions import uses_image_text_pipeline

    if not shots:
        return
    if uses_image_text_pipeline(style_mode):
        problems = validate_shots_voice_content(shots)
        if problems:
            labels: list[str] = []
            for shot in shots:
                issues = problems.get(shot.id)
                if not issues:
                    continue
                labels.append(f"镜{shot.order + 1}")
            detail = "；".join(problems[next(iter(problems))][:3])
            raise ValueError(
                f"以下镜头缺少配音幕（audio_tracks[kind=voice].clips[].text）："
                f"{'、'.join(labels[:8])}{' 等' + str(len(labels)) + '镜' if len(labels) > 8 else ''}；"
                f"{detail}；"
                "请将旁白/对白写入镜内 voice clip text，并按说话人拆分 clip："
                "角色对白填 character_ref（load_context.characters 的 txt_*），旁白留空 character_ref"
            )
    if store and script_id:
        speaker_problems = validate_shots_voice_speakers(shots, store, script_id)
        if speaker_problems:
            labels = [
                f"镜{shot.order + 1}"
                for shot in shots
                if speaker_problems.get(shot.id)
            ]
            detail = "；".join(speaker_problems[next(iter(speaker_problems))][:2])
            raise ValueError(
                f"以下镜头配音幕说话人无效："
                f"{'、'.join(labels[:8])}{' 等' + str(len(labels)) + '镜' if len(labels) > 8 else ''}；"
                f"{detail}；"
                "character_ref 须为空（旁白）或引用 load_context.characters 中已生成的角色 txt_*"
            )


def _parse_element_refs(raw: Any) -> dict[str, list[str]]:
    """解析画面元素引用 {character/scene/prop: [id...]}。"""
    out: dict[str, list[str]] = {}
    if not isinstance(raw, dict):
        return out
    for key in ("scene", "character", "prop"):
        val = raw.get(key) or []
        ids = [str(v) for v in (val if isinstance(val, list) else [val]) if v]
        if ids:
            out[key] = ids
    return out


def _parse_sub_shot_image(raw: Any) -> ShotSubShotImage | None:
    """解析画面图片意图（static/video）；保留客户端传入的 id。"""
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or "static").strip().lower()
    if kind not in ("static", "video"):
        kind = "static"
    source_ids = raw.get("source_media_ids") or []
    source_media_ids = [str(x) for x in source_ids if x] if isinstance(source_ids, list) else []
    raw_id = str(raw.get("id") or "").strip()
    fields: dict[str, Any] = {
        "kind": kind,
        "frame_asset_id": str(raw.get("frame_asset_id") or "").strip(),
        "source_media_ids": source_media_ids,
        "media_id": str(raw.get("media_id") or "").strip(),
        "video_prompt": str(raw.get("video_prompt") or "").strip(),
        "prompt_locked": bool(raw.get("prompt_locked", False)),
        "start_ms": max(0, int(raw.get("start_ms", 0))),
        "end_ms": max(0, int(raw.get("end_ms", 0))),
    }
    if raw_id:
        fields["id"] = raw_id
    return ShotSubShotImage(**fields)


def _parse_sub_shot_images(raw_item: dict[str, Any]) -> list[ShotSubShotImage]:
    """解析子镜关联图片列表；兼容旧版单 image 字段；重复 id 重新分配。"""
    images_raw = raw_item.get("images")
    if isinstance(images_raw, list) and images_raw:
        out: list[ShotSubShotImage] = []
        seen: set[str] = set()
        for item in images_raw:
            parsed = _parse_sub_shot_image(item)
            if not parsed:
                continue
            if parsed.id in seen:
                parsed = parsed.model_copy(update={"id": new_id("ssi")})
            seen.add(parsed.id)
            out.append(parsed)
        return out
    legacy = _parse_sub_shot_image(raw_item.get("image"))
    return [legacy] if legacy else []


def _parse_sub_shot_videos(raw_item: dict[str, Any]) -> list[ShotSubShotVideo]:
    """解析子镜关联视频列表。"""
    videos_raw = raw_item.get("videos")
    if not isinstance(videos_raw, list):
        return []
    out: list[ShotSubShotVideo] = []
    for item in videos_raw:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("source_kind") or "video").strip().lower()
        out.append(
            ShotSubShotVideo(
                id=str(item.get("id") or new_id("ssv")),
                media_id=str(item.get("media_id") or "").strip(),
                start_ms=max(0, int(item.get("start_ms", 0))),
                end_ms=max(0, int(item.get("end_ms", 0))),
                source_kind=kind if kind in ("video", "still") else "video",  # type: ignore[arg-type]
                camera_motion=_normalize_shot_camera_motion(item.get("camera_motion")),
            )
        )
    return out


def _parse_sub_shots(raw: Any) -> list[ShotSubShot]:
    """解析镜内子镜轨（剧本时间轴时段）。"""
    from core.edit.sub_shot_produce import coerce_produce_mode

    _VALID_PRODUCE = {"still", "text2video", "img2video", "still_edit", "ai_video", "hybrid"}
    sub_shots: list[ShotSubShot] = []
    if not isinstance(raw, list):
        return sub_shots
    for item in raw:
        if not isinstance(item, dict):
            continue
        raw_mode = str(item.get("produce_mode") or "").strip()
        produce_mode_from_input = raw_mode in _VALID_PRODUCE
        mode = coerce_produce_mode(raw_mode) if produce_mode_from_input else "still"
        sub = ShotSubShot(
            id=str(item.get("id") or new_id("ssb")),
            start_ms=max(0, int(item.get("start_ms", 0))),
            end_ms=max(0, int(item.get("end_ms", 0))),
            description=str(item.get("description", "")).strip(),
            element_refs=_parse_element_refs(item.get("element_refs")),
            camera_motion=_normalize_shot_camera_motion(item.get("camera_motion")),
            images=_parse_sub_shot_images(item),
            videos=_parse_sub_shot_videos(item),
            produce_mode=mode,
            produce_rationale=str(item.get("produce_rationale") or "").strip(),
        )
        sub_shots.append(
            finalize_sub_shot(sub, produce_mode_from_input=produce_mode_from_input)
        )
    return sub_shots


def _parse_video_tracks(raw: Any) -> list[ShotVideoTrack]:
    """解析镜内视频轨。"""
    tracks: list[ShotVideoTrack] = []
    if not isinstance(raw, list):
        return tracks
    for i, t in enumerate(raw):
        if not isinstance(t, dict):
            continue
        clips_raw = t.get("clips") or []
        clips: list[ShotVideoClip] = []
        if isinstance(clips_raw, list):
            for c in clips_raw:
                if not isinstance(c, dict):
                    continue
                kind = str(c.get("source_kind") or "still").strip().lower()
                clips.append(
                    ShotVideoClip(
                        id=str(c.get("id") or new_id("svc")),
                        start_ms=max(0, int(c.get("start_ms", 0))),
                        end_ms=max(0, int(c.get("end_ms", 0))),
                        source_sub_shot_id=str(c.get("source_sub_shot_id") or "").strip(),
                        media_id=str(c.get("media_id") or "").strip(),
                        source_kind=kind if kind in ("video", "still") else "still",  # type: ignore[arg-type]
                        camera_motion=_normalize_shot_camera_motion(c.get("camera_motion")),
                        edit_description=str(c.get("edit_description", "")).strip(),
                    )
                )
        tracks.append(
            ShotVideoTrack(
                id=str(t.get("id") or new_id("svt")),
                name=str(t.get("name", "")).strip(),
                z_index=int(t.get("z_index", i)),
                clips=clips,
            )
        )
    return tracks


def _parse_audio_tracks(raw: Any) -> list[ShotAudioTrack]:
    """解析镜内音频轨（voice/background）。"""
    tracks: list[ShotAudioTrack] = []
    if not isinstance(raw, list):
        return tracks
    for t in raw:
        if not isinstance(t, dict):
            continue
        kind = str(t.get("kind") or "voice").strip().lower()
        if kind not in ("voice", "background"):
            kind = "voice"
        clips_raw = t.get("clips") or []
        clips: list[ShotAudioClip] = []
        if isinstance(clips_raw, list):
            for c in clips_raw:
                if not isinstance(c, dict):
                    continue
                try:
                    volume = float(c.get("volume", 1.0))
                except (TypeError, ValueError):
                    volume = 1.0
                clips.append(
                    ShotAudioClip(
                        id=str(c.get("id") or new_id("sac")),
                        start_ms=max(0, int(c.get("start_ms", 0))),
                        end_ms=max(0, int(c.get("end_ms", 0))),
                        media_id=str(c.get("media_id") or "").strip(),
                        text=str(c.get("text", "")).strip(),
                        character_ref=str(c.get("character_ref") or "").strip(),
                        voice=str(c.get("voice") or "").strip(),
                        volume=volume,
                    )
                )
        tracks.append(
            ShotAudioTrack(
                id=str(t.get("id") or new_id("sat")),
                name=str(t.get("name", "")).strip(),
                kind=kind,  # type: ignore[arg-type]
                clips=clips,
            )
        )
    return tracks


def _parse_subtitles(raw: Any) -> list[ShotSubtitle]:
    """解析镜内字幕。"""
    subs: list[ShotSubtitle] = []
    if not isinstance(raw, list):
        return subs
    for s in raw:
        if not isinstance(s, dict):
            continue
        text = str(s.get("text", "")).strip()
        if not text:
            continue
        subs.append(
            ShotSubtitle(
                id=str(s.get("id") or new_id("ssub")),
                text=text,
                start_ms=max(0, int(s.get("start_ms", 0))),
                end_ms=max(0, int(s.get("end_ms", 0))),
            )
        )
    return subs


def _derive_video_tracks_from_sub_shots(sub_shots: list[ShotSubShot]) -> list[ShotVideoTrack]:
    """无显式视频轨时，从子镜轨派生 z0 视频轨（每子镜一个待绑定 clip）。"""
    if not sub_shots:
        return []
    clips = []
    for v in sub_shots:
        img = first_sub_shot_image(v)
        clips.append(
            ShotVideoClip(
                id=new_id("svc"),
                start_ms=v.start_ms,
                end_ms=v.end_ms,
                source_sub_shot_id=v.id,
                media_id=(img.media_id if img else ""),
                source_kind=("video" if (img and img.kind == "video") else "still"),
                camera_motion=v.camera_motion,
            )
        )
    return [ShotVideoTrack(id=new_id("svt"), name="主画面", z_index=0, clips=clips)]


def _shot_duration_from_parts(
    provided: int,
    sub_shots: list[ShotSubShot],
    video_tracks: list[ShotVideoTrack],
    audio_tracks: list[ShotAudioTrack],
    subtitles: list[ShotSubtitle],
) -> int:
    """按镜内各轨最大终点与显式值取较大者作为镜时长。"""
    end = max(0, int(provided or 0))
    for v in sub_shots:
        end = max(end, int(v.end_ms or 0))
    for t in video_tracks:
        for c in t.clips:
            end = max(end, int(c.end_ms or 0))
    for t in audio_tracks:
        for c in t.clips:
            end = max(end, int(c.end_ms or 0))
    for s in subtitles:
        end = max(end, int(s.end_ms or 0))
    return end or 3000


_visuals_alias_warned = False


def parse_single_shot_from_data(raw: dict[str, Any]) -> Shot | None:
    """从单个 dict 解析一个镜内多轨 Shot（供结构性复核 ops 复用）。"""
    global _visuals_alias_warned
    if not isinstance(raw, dict):
        return None
    sub_shots_raw = raw.get("sub_shots")
    if sub_shots_raw is None and raw.get("visuals") is not None:
        sub_shots_raw = raw.get("visuals")
        if not _visuals_alias_warned:
            get_logger(__name__).warning(
                "parse_shots 收到已废弃字段 visuals，已映射为 sub_shots；请同步 prompt 输出"
            )
            _visuals_alias_warned = True
    sub_shots = _parse_sub_shots(sub_shots_raw)
    video_tracks = _parse_video_tracks(raw.get("video_tracks"))
    if not video_tracks and sub_shots:
        video_tracks = _derive_video_tracks_from_sub_shots(sub_shots)
    audio_tracks = _parse_audio_tracks(raw.get("audio_tracks"))
    subtitles = _parse_subtitles(raw.get("subtitles"))
    duration = _shot_duration_from_parts(
        int(raw.get("duration_ms", 0)), sub_shots, video_tracks, audio_tracks, subtitles
    )
    return Shot(
        id=str(raw.get("id") or new_id("shot")),
        order=int(raw.get("order", 0)),
        duration_ms=duration,
        title=str(raw.get("title", "")).strip(),
        summary=str(raw.get("summary", "")).strip(),
        sub_shots=sub_shots,
        video_tracks=video_tracks,
        audio_tracks=audio_tracks,
        subtitles=subtitles,
        plan_note=str(raw.get("plan_note", "")).strip(),
    )


def parse_shots_from_data(
    store: MemoryStore,
    shots_data: Any,
) -> list[Shot]:
    """从 LLM 输出解析镜内多轨镜头列表。"""
    del store  # 新模型不再需要 asset_refs 归一化
    shots: list[Shot] = []
    if not isinstance(shots_data, list):
        return shots
    for i, raw in enumerate(shots_data):
        if not isinstance(raw, dict):
            continue
        shot = parse_single_shot_from_data({**raw, "order": raw.get("order", i)})
        if shot is None:
            continue
        # 空镜（无画面且无音频文案）跳过
        if not shot.sub_shots and not any(
            c.text for t in shot.audio_tracks for c in t.clips
        ):
            continue
        shots.append(shot)
    return normalize_shot_orders(shots) if shots else []


def _create_frame_assets_from_data(
    store: MemoryStore,
    ctx: AgentRunContext,
    frames_data: list[Any],
    pending_shots: list[Shot],
) -> tuple[list[TextAsset], list[Shot], list[dict[str, str]]]:
    """按子镜创建 frame 文字资产并回填 sub_shot.images[].frame_asset_id。"""
    from core.assets.service import finalize_text_asset_content_for_store
    from core.llm.agent.script_assets import link_script_asset

    script_id = ctx.script_id
    project_id = str(ctx.work_context.get("project_id", ""))
    if not project_id:
        script = store.get_script(script_id)
        project_id = script.project_id if script else ""

    shots_map = {s.id: s.model_copy(deep=True) for s in pending_shots}
    shots_by_order = {s.order: s.id for s in pending_shots}
    created: list[TextAsset] = []
    frame_links: list[dict[str, str]] = []

    for raw in frames_data:
        if not isinstance(raw, dict):
            continue
        shot_id = str(raw.get("shot_id", "")).strip()
        shot: Shot | None = shots_map.get(shot_id) if shot_id else None
        if shot is None and raw.get("order") is not None:
            oid = shots_by_order.get(int(raw.get("order")))
            if oid:
                shot = shots_map.get(oid)
        if shot is None or not shot.sub_shots:
            continue

        target_sub_shot_id = str(
            raw.get("sub_shot_id") or raw.get("visual_id") or ""
        ).strip()
        target_idx = None
        if target_sub_shot_id:
            for idx, v in enumerate(shot.sub_shots):
                if v.id == target_sub_shot_id:
                    target_idx = idx
                    break
        if target_idx is None and raw.get("sub_shot_index") is not None:
            sub_idx = int(raw.get("sub_shot_index"))
            if 0 <= sub_idx < len(shot.sub_shots):
                target_idx = sub_idx
                if target_sub_shot_id:
                    get_logger(__name__).warning(
                        "create_frames 未识别 sub_shot_id=%s，改用 sub_shot_index=%s（镜%s）",
                        target_sub_shot_id,
                        sub_idx,
                        shot.order + 1,
                    )
        if target_idx is None:
            if not target_sub_shot_id:
                raise ValueError(
                    f"create_frames 缺少 sub_shot_id（镜{shot.order + 1}）；"
                    "请从 create_shots/get_plan 返回 JSON 读取 sub_shots[].id，"
                    "或提供 order + sub_shot_index"
                )
            raise ValueError(
                f"create_frames 未找到子镜 {target_sub_shot_id}（镜{shot.order + 1}）；"
                "请调用 get_plan 获取系统生成的 sub_shot_id，或使用 order + sub_shot_index"
            )
        sub = shot.sub_shots[target_idx]

        element_refs = _parse_element_refs(raw.get("element_refs")) or dict(sub.element_refs)
        image_prompt = str(
            raw.get("image_prompt") or raw.get("description", "") or sub.description
        ).strip()
        summary = str(raw.get("summary", "")).strip() or image_prompt[:80]
        content: dict[str, Any] = {
            "summary": summary,
            "image_prompt": image_prompt,
            "notes": str(raw.get("notes", "")).strip(),
            "element_refs": element_refs,
            "variant_refs": {},
            "shot_id": shot.id,
            "prompt_locked": True,
            "reference_order": raw.get("reference_order")
            or ["scene", "character", "prop"],
        }
        name = str(raw.get("name", "")).strip() or f"剧本画面·镜{shot.order + 1}"
        asset = TextAsset(
            project_id=project_id,
            script_id=script_id,
            scope=AssetScope.SCRIPT_PRIVATE,
            type=TextAssetType.FRAME,
            name=name,
            content=content,
            source_script_id=script_id,
            reuse_policy="private",
        )
        # 已锁定 image_prompt 时保留 Agent 原文，不做组装覆盖
        asset.content = finalize_text_asset_content_for_store(
            store, asset, content, force_recompose=not bool(content.get("prompt_locked"))
        )
        store.add_text_asset(asset)
        link_script_asset(store, script_id, asset.id)
        created.append(asset)

        frame_links.append(
            {
                "shot_id": shot.id,
                "sub_shot_id": sub.id,
                "frame_asset_id": asset.id,
            }
        )

        # 回填子镜图片引用的 frame_asset_id
        new_image = ShotSubShotImage(frame_asset_id=asset.id)
        new_sub_shots = list(shot.sub_shots)
        new_sub_shots[target_idx] = append_sub_shot_image(sub, new_image)
        shots_map[shot.id] = shot.model_copy(update={"sub_shots": new_sub_shots})

    updated = normalize_shot_orders([shots_map[s.id] for s in pending_shots if s.id in shots_map])
    return created, updated, frame_links


def _create_video_clip_assets_from_data(
    store: MemoryStore,
    ctx: AgentRunContext,
    clips_data: list[Any],
    pending_shots: list[Shot],
) -> tuple[list[TextAsset], list[Shot], list[dict[str, str]]]:
    """按子镜创建 video_clip 文字资产并回填 sub_shot.videos[].video_clip_asset_id。"""
    from core.assets.service import finalize_text_asset_content_for_store
    from core.llm.agent.script_assets import link_script_asset

    script_id = ctx.script_id
    project_id = str(ctx.work_context.get("project_id", ""))
    if not project_id:
        script = store.get_script(script_id)
        project_id = script.project_id if script else ""

    shots_map = {s.id: s.model_copy(deep=True) for s in pending_shots}
    shots_by_order = {s.order: s.id for s in pending_shots}
    created: list[TextAsset] = []
    clip_links: list[dict[str, str]] = []

    for raw in clips_data:
        if not isinstance(raw, dict):
            continue
        shot_id = str(raw.get("shot_id", "")).strip()
        shot: Shot | None = shots_map.get(shot_id) if shot_id else None
        if shot is None and raw.get("order") is not None:
            oid = shots_by_order.get(int(raw.get("order")))
            if oid:
                shot = shots_map.get(oid)
        if shot is None or not shot.sub_shots:
            continue

        target_sub_shot_id = str(
            raw.get("sub_shot_id") or raw.get("visual_id") or ""
        ).strip()
        target_idx = None
        if target_sub_shot_id:
            for idx, v in enumerate(shot.sub_shots):
                if v.id == target_sub_shot_id:
                    target_idx = idx
                    break
        if target_idx is None and raw.get("sub_shot_index") is not None:
            sub_idx = int(raw.get("sub_shot_index"))
            if 0 <= sub_idx < len(shot.sub_shots):
                target_idx = sub_idx
                if target_sub_shot_id:
                    get_logger(__name__).warning(
                        "create_video_clips 未识别 sub_shot_id=%s，改用 sub_shot_index=%s（镜%s）",
                        target_sub_shot_id,
                        sub_idx,
                        shot.order + 1,
                    )
        if target_idx is None:
            if not target_sub_shot_id:
                raise ValueError(
                    f"create_video_clips 缺少 sub_shot_id（镜{shot.order + 1}）；"
                    "请从 create_shots/get_plan 返回 JSON 读取 sub_shots[].id，"
                    "或提供 order + sub_shot_index"
                )
            raise ValueError(
                f"create_video_clips 未找到子镜 {target_sub_shot_id}（镜{shot.order + 1}）；"
                "请调用 get_plan 获取系统生成的 sub_shot_id，或使用 order + sub_shot_index"
            )
        sub = shot.sub_shots[target_idx]

        element_refs = _parse_element_refs(raw.get("element_refs")) or dict(sub.element_refs)
        media_refs_raw = raw.get("media_refs") or []
        media_refs = (
            [str(x).strip() for x in media_refs_raw if str(x).strip()]
            if isinstance(media_refs_raw, list)
            else []
        )
        video_prompt = str(
            raw.get("video_prompt") or raw.get("description", "") or sub.description
        ).strip()
        content: dict[str, Any] = {
            "summary": str(raw.get("summary", "")).strip() or video_prompt[:80],
            "video_prompt": video_prompt,
            "notes": str(raw.get("notes", "")).strip(),
            "video_mode": "auto",
            "camera_motion": (sub.camera_motion or "static").strip(),
            "element_refs": element_refs,
            "media_refs": media_refs,
            "reference_order": raw.get("reference_order")
            or ["scene", "character", "prop", "frame", "media"],
            "shot_id": shot.id,
            "sub_shot_id": sub.id,
            "prompt_locked": True,
        }
        name = str(raw.get("name", "")).strip() or f"视频片段·镜{shot.order + 1}"
        asset = TextAsset(
            project_id=project_id,
            script_id=script_id,
            scope=AssetScope.SCRIPT_PRIVATE,
            type=TextAssetType.VIDEO_CLIP,
            name=name,
            content=content,
            source_script_id=script_id,
            reuse_policy="private",
        )
        asset.content = finalize_text_asset_content_for_store(
            store, asset, content, force_recompose=not bool(content.get("prompt_locked"))
        )
        store.add_text_asset(asset)
        link_script_asset(store, script_id, asset.id)
        created.append(asset)

        clip_links.append(
            {
                "shot_id": shot.id,
                "sub_shot_id": sub.id,
                "video_clip_asset_id": asset.id,
            }
        )

        new_video = ShotSubShotVideo(
            video_clip_asset_id=asset.id,
            camera_motion=content.get("camera_motion") or sub.camera_motion,
        )
        new_sub_shots = list(shot.sub_shots)
        new_sub_shots[target_idx] = append_sub_shot_video(sub, new_video)
        shots_map[shot.id] = shot.model_copy(update={"sub_shots": new_sub_shots})

    updated = normalize_shot_orders([shots_map[s.id] for s in pending_shots if s.id in shots_map])
    return created, updated, clip_links


def build_action_system_prompt(
    agent_name: str,
    profile: PromptProfile | str = PromptProfile.DEFAULT,
) -> str:
    return build_action_system(agent_name, profile)



def _persist_media(
    store: MemoryStore,
    *,
    project_id: str,
    script_id: str,
    media_type: MediaAssetType,
    name: str,
    url: str,
    asset_id: str | None = None,
    source_asset_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> MediaAsset:
    media = MediaAsset(
        id=asset_id or new_id("media"),
        project_id=project_id,
        script_id=script_id,
        type=media_type,
        name=name,
        url=url,
        source_asset_id=source_asset_id,
        status=AssetStatus.GENERATED,
        metadata=metadata or {},
    )
    from core.store.media_storage import persist_media_url_to_disk

    original_url = url
    media.url = persist_media_url_to_disk(
        project_id=project_id,
        script_id=script_id,
        media_id=media.id,
        url=media.url,
        media_type=media_type.value,
    )
    if original_url.startswith(("http://", "https://")) and media.url != original_url:
        media.metadata["source_url"] = original_url
    store.add_media_asset(media)
    if source_asset_id:
        ref = AssetReference(
            source_id=source_asset_id,
            target_id=media.id,
            relation=RelationType.GENERATES,
            script_id=script_id,
        )
        store.add_reference(ref)
    return media


def _is_placeholder_url(url: str) -> bool:
    u = url.strip().lower()
    if not u:
        return True
    if "example.com" in u:
        return True
    if u.startswith("/assets/"):
        return True
    if u.startswith("placeholder:"):
        return True
    if u.startswith("timeline://"):
        return True
    return False


def _maybe_apply_chroma_key_to_media(
    media: MediaAsset,
    *,
    project_id: str,
    script_id: str,
    asset_type: Any,
) -> None:
    """character/prop 生图落盘后绿幕抠图 → 透明 PNG。"""
    from core.assets.chroma_key import apply_chroma_key_to_media
    from core.logging.setup import log_stage

    if apply_chroma_key_to_media(
        media,
        project_id=project_id,
        script_id=script_id,
        asset_type=asset_type,
    ):
        log_stage(
            logger,
            "image.chroma_key",
            "绿幕抠图完成",
            media_id=media.id,
            path=media.url,
        )
    elif asset_type is not None:
        from core.assets.chroma_key import is_chroma_eligible_text_type

        if is_chroma_eligible_text_type(asset_type):
            log_stage(
                logger,
                "image.chroma_key",
                "绿幕抠图失败，保留原图",
                media_id=media.id,
                error=media.metadata.get("chroma_key_error", ""),
            )


def persist_single_generated_image(
    store: MemoryStore,
    ctx: AgentRunContext,
    item: dict[str, Any],
) -> MediaAsset | None:
    """落盘单张 generate_images 结果，关联文字资产变体；primary 仅 base。"""
    url = str(item.get("url", ""))
    if _is_placeholder_url(url):
        return None
    script_id = str(ctx.work_context.get("script_id") or ctx.script_id)
    project_id = str(ctx.work_context.get("project_id", ""))
    source_id = item.get("source_text_asset_id")
    source_id_str = str(source_id) if source_id else None
    variant_id = str(item.get("variant_id", "")).strip()
    variant_kind = str(item.get("variant_kind", "")).strip()
    meta: dict[str, Any] = {}
    image_prompt = str(item.get("image_prompt", "")).strip()
    if source_id_str:
        src = store.get_text_asset(source_id_str)
        if src and is_image_text_asset(src.type):
            content = normalize_image_text_content(src.type, src.content)
            content = ensure_image_variants(content, primary_media_id=src.primary_media_id)
            if variant_id:
                v = find_variant(content, variant_id)
                if v:
                    variant_kind = v.kind
                    image_prompt = image_prompt or str(v.image_prompt).strip()
            image_prompt = image_prompt or str(content.get("image_prompt", "")).strip()
            meta = {
                "generation_prompt": image_prompt,
                "negative_prompt": str(content.get("negative_prompt", "")).strip(),
                "prompt_version": content.get("prompt_version", 0),
                "source_text_asset_id": source_id_str,
            }
            if variant_id:
                meta["variant_id"] = variant_id
                meta["variant_kind"] = variant_kind
                ref_mid = str(item.get("reference_media_id", "")).strip()
                if ref_mid:
                    meta["reference_media_id"] = ref_mid
    media_id = str(item.get("asset_id") or new_id("media"))
    name = str(item.get("name", "image"))
    meta.setdefault("source", "agnes")
    source_asset_type: Any = None
    if source_id_str:
        src_for_type = store.get_text_asset(source_id_str)
        if src_for_type:
            source_asset_type = src_for_type.type
    media = _persist_media(
        store,
        project_id=project_id,
        script_id=script_id,
        media_type=MediaAssetType.IMAGE,
        name=name,
        url=url,
        asset_id=media_id,
        source_asset_id=source_id_str,
        metadata=meta,
    )
    _maybe_apply_chroma_key_to_media(
        media,
        project_id=project_id,
        script_id=script_id,
        asset_type=source_asset_type,
    )
    schedule_save(store)
    if source_id_str:
        src = store.get_text_asset(source_id_str)
        if src and src.type == TextAssetType.FRAME:
            src.primary_media_id = media.id
            store.update_text_asset(src)
            from core.edit.shot_media_bind import bind_frame_media_to_plan

            bind_frame_media_to_plan(store, script_id, source_id_str, media.id)
        elif src and is_image_text_asset(src.type):
            from core.models.image_text_asset import get_base_variant

            content = normalize_image_text_content(src.type, src.content)
            content = ensure_image_variants(content, primary_media_id=src.primary_media_id)
            target_vid = variant_id
            if not target_vid:
                base_v = get_base_variant(content)
                target_vid = base_v.id if base_v else ""
            if target_vid:
                v = find_variant(content, target_vid)
                is_base = bool(v and v.kind == "base")
                content = update_variant_in_content(
                    content,
                    target_vid,
                    media_id=media.id,
                    status="ready",
                )
                if is_base:
                    src.primary_media_id = media.id
            src.content = content
            store.update_text_asset(src)
    ctx.outputs.append(
        StepOutput(
            kind="image",
            label=name,
            asset_id=media.id,
            url=media.url,
        )
    )
    return media


_persist_image_thread_lock = threading.Lock()


async def persist_single_generated_image_async(
    store: MemoryStore,
    ctx: AgentRunContext,
    item: dict[str, Any],
) -> MediaAsset | None:
    """异步落盘生图结果：下载与绿幕抠图在线程池执行，不阻塞事件循环。"""

    def _run() -> MediaAsset | None:
        with _persist_image_thread_lock:
            return persist_single_generated_image(store, ctx, item)

    return await asyncio.to_thread(_run)


def _coerce_asset_content(action: str, raw: Any, observation: str) -> dict[str, Any]:
    """将 LLM 返回的 content（可能是 str 或 dict）规范为 TextAsset 所需的 dict。"""
    return normalize_asset_content(raw, action=action, observation=observation)


def _asset_content_summary(content: dict[str, Any], asset_type: Any = None) -> str:
    if asset_type and is_image_text_asset(asset_type):
        prompt = str(content.get("image_prompt", "")).strip()
        if prompt:
            if len(prompt) > IMAGE_PROMPT_SUMMARY_MAX:
                return prompt[:IMAGE_PROMPT_SUMMARY_MAX] + "…"
            return prompt
    for key in ("summary", "text", "description", "appearance", "content"):
        val = content.get(key)
        if isinstance(val, str) and val.strip():
            text = val.strip()
            if len(text) > ASSET_SUMMARY_MAX:
                return text[:ASSET_SUMMARY_MAX] + "…"
            return text
    return ""


def _build_store_context_block(store: MemoryStore, work_context: dict[str, Any]) -> str:
    script_id = str(work_context.get("script_id", ""))
    lines: list[str] = []

    user_message = work_context.get("user_message")
    if user_message:
        lines.append(f"用户创意：{user_message}")

    script = store.get_script(script_id) if script_id else None
    if script and script.content_md.strip():
        md = script.content_md.strip()
        if len(md) > SCRIPT_MD_CONTEXT_MAX:
            md = md[:SCRIPT_MD_CONTEXT_MAX] + "…"
        lines.append(f"当前剧本正文：\n{md}")

    assets = store.list_assets_for_script(script_id) if script_id else []
    if assets:
        lines.append("已有文字资产：")
        for asset in assets:
            summary = _asset_content_summary(asset.content, asset.type)
            suffix = f" — {summary}" if summary else ""
            lines.append(f"- [{asset.type.value}] {asset.name} ({asset.id}){suffix}")

    media = store.list_media_for_script(script_id) if script_id else []
    if media:
        lines.append("已有媒体资产：")
        for m in media:
            url_part = f" url={m.url}" if m.url else ""
            src = f" src={m.source_asset_id}" if m.source_asset_id else ""
            lines.append(f"- [{m.type.value}] {m.name} ({m.id}){src}{url_part}")

    vp = store.get_video_plan_for_script(script_id) if script_id else None
    if vp and vp.shots:
        lines.append(f"已有分镜：{len(vp.shots)} 镜（persist_plan 前可能为草稿）")
        for shot in sorted(vp.shots, key=lambda s: s.order)[:3]:
            first_text = ""
            for track in shot.audio_tracks:
                for clip in track.clips:
                    if clip.text:
                        first_text = clip.text
                        break
                if first_text:
                    break
            visual_desc = shot.sub_shots[0].description if shot.sub_shots else ""
            summary = (first_text or visual_desc or shot.summary)[:40]
            lines.append(
                f"  - 镜{shot.order + 1}: {summary}… 画面{len(shot.sub_shots)}/音轨{len(shot.audio_tracks)}"
            )

    return "\n".join(lines) + ("\n" if lines else "")


def _append_character_tts_hint(
    store_block: str,
    *,
    action: str,
) -> str:
    """为角色创建/更新行动附加 TTS 可选音色说明。"""
    if action not in ("create_character", "update_character"):
        return store_block
    from core.llm.prompt.tts_voice_context import (
        build_tts_voice_context,
        format_tts_voice_hint_block,
    )

    hint = format_tts_voice_hint_block(build_tts_voice_context())
    if not hint:
        return store_block
    return f"{store_block}{hint}"


def build_action_user_content(
    *,
    store: MemoryStore,
    role_prompt: str,
    display_name: str,
    action: str,
    task_brief: str,
    observations: list[str],
    completed_actions: set[str],
    work_context: dict[str, Any],
    history_summary: str = "",
) -> str:
    ctx = AgentRunContext(
        task_brief=task_brief,
        work_context=work_context,
        script_id=str(work_context.get("script_id", "")),
        step_id="",
        agent_name="",
        completed_actions=completed_actions,
        observations=observations,
        history_summary=history_summary,
    )
    store_block = _build_store_context_block(store, work_context)
    store_block = _append_character_tts_hint(store_block, action=action)
    slots = AgentContextManager.sub_agent.build_action_slots(
        ctx,
        store,
        role_prompt=role_prompt,
        display_name=display_name,
        action=action,
        store_context_block=store_block,
    )
    return build_action_user(slots)


def apply_action_result(
    store: MemoryStore,
    agent_name: str,
    action: str,
    ctx: AgentRunContext,
    data: dict[str, Any],
) -> str:
    """将 LLM JSON 结果应用到存储，返回 observation。"""
    observation = str(data.get("observation", "")).strip()
    script_id = str(ctx.work_context.get("script_id") or ctx.script_id)
    project_id = str(ctx.work_context.get("project_id", ""))
    user_message = str(ctx.work_context.get("user_message", "")).strip()

    if action == "parse_brief":
        script = store.get_script(script_id)
        content_md = data.get("content_md") or data.get("script_md")
        if script and content_md:
            script.content_md = str(content_md)
        elif script and not script.content_md:
            title = script.title or user_message or "未命名剧本"
            body = observation or user_message or "待补充剧情"
            script.content_md = f"# {title}\n\n{body}"
        if script:
            next_title = apply_script_title_if_allowed(script.title, data.get("title"))
            if next_title is not None:
                script.title = next_title
        if script and data.get("duration_sec") is not None:
            try:
                script.duration_sec = int(data["duration_sec"])
            except (TypeError, ValueError):
                pass
        if not observation:
            observation = f"已解析任务简报并设计剧本，剧本 ID={script_id}。"

    elif action == "update_script":
        script = store.get_script(script_id)
        if not script:
            observation = observation or f"剧本 {script_id} 不存在。"
        else:
            next_title = apply_script_title_if_allowed(script.title, data.get("title"))
            if next_title is not None:
                script.title = next_title
            content_md = data.get("content_md") or data.get("script_md")
            if content_md:
                script.content_md = str(content_md)
            if data.get("duration_sec") is not None:
                try:
                    script.duration_sec = int(data["duration_sec"])
                except (TypeError, ValueError):
                    pass
            if not observation:
                observation = f"已更新剧本「{script.title}」正文。"

    elif action == "create_plot":
        plot = create_text_asset_for_action(
            store,
            action=action,
            project_id=project_id,
            script_id=script_id,
            asset_name=str(data.get("asset_name", "剧情段落1")),
            content=extract_llm_content_field(data, action),
            observation=observation,
        ).asset
        ctx.outputs.append(StepOutput(kind="json", label="plot", asset_id=plot.id))
        if not observation:
            observation = f"已创建剧情资产 {plot.id}，并关联到剧本。"

    elif action == "create_character":
        outcome = create_text_asset_for_action(
            store,
            action=action,
            project_id=project_id,
            script_id=script_id,
            asset_name=str(data.get("asset_name", "主角")),
            content=extract_llm_content_field(data, action),
            observation=observation,
        )
        character = outcome.asset
        ctx.outputs.append(
            StepOutput(kind="json", label="character", asset_id=character.id)
        )
        if not observation:
            if outcome.rag_decision == "reuse":
                observation = f"已复用人物资产 {character.id}（{character.name}）。{outcome.rag_reason}"
            elif outcome.rag_decision == "fork":
                observation = f"已 fork 人物资产 {character.id}。{outcome.rag_reason}"
            else:
                observation = f"已创建人物资产 {character.id}，并关联到剧本。"

    elif action == "create_scene":
        outcome = create_text_asset_for_action(
            store,
            action=action,
            project_id=project_id,
            script_id=script_id,
            asset_name=str(data.get("asset_name", "场景")),
            content=extract_llm_content_field(data, action),
            observation=observation,
        )
        scene = outcome.asset
        ctx.outputs.append(StepOutput(kind="json", label="scene", asset_id=scene.id))
        if not observation:
            if outcome.rag_decision == "reuse":
                observation = f"已复用场景资产 {scene.id}（{scene.name}）。{outcome.rag_reason}"
            elif outcome.rag_decision == "fork":
                observation = f"已 fork 场景资产 {scene.id}。{outcome.rag_reason}"
            else:
                observation = f"已创建场景资产 {scene.id}，并关联到剧本。"

    elif action == "create_prop":
        outcome = create_text_asset_for_action(
            store,
            action=action,
            project_id=project_id,
            script_id=script_id,
            asset_name=str(data.get("asset_name", "道具")),
            content=extract_llm_content_field(data, action),
            observation=observation,
        )
        prop = outcome.asset
        ctx.outputs.append(StepOutput(kind="json", label="prop", asset_id=prop.id))
        if not observation:
            if outcome.rag_decision == "reuse":
                observation = f"已复用道具资产 {prop.id}（{prop.name}）。{outcome.rag_reason}"
            elif outcome.rag_decision == "fork":
                observation = f"已 fork 道具资产 {prop.id}。{outcome.rag_reason}"
            else:
                observation = f"已创建道具资产 {prop.id}，并关联到剧本。"

    elif action in (
        "update_plot",
        "update_character",
        "update_scene",
        "update_prop",
    ):
        asset_id = str(data.get("asset_id", "")).strip()
        if not asset_id:
            observation = observation or "更新失败：缺少 asset_id。"
        else:
            try:
                asset = update_text_asset_for_action(
                    store,
                    action=action,
                    script_id=script_id,
                    asset_id=asset_id,
                    asset_name=str(data["asset_name"]) if data.get("asset_name") else None,
                    content=extract_llm_content_field(data, action),
                    observation=observation,
                )
                ctx.outputs.append(
                    StepOutput(kind="json", label=asset.type.value, asset_id=asset.id)
                )
                if not observation:
                    observation = f"已更新{asset.type.value}资产 {asset.id}。"
            except Exception as e:
                observation = observation or f"更新失败：{e}"

    elif action in (
        "delete_plot",
        "delete_character",
        "delete_scene",
        "delete_prop",
    ):
        asset_id = str(data.get("asset_id", "")).strip()
        if not asset_id:
            observation = observation or "删除失败：缺少 asset_id。"
        else:
            try:
                delete_text_asset_for_action(
                    store,
                    action=action,
                    script_id=script_id,
                    asset_id=asset_id,
                )
                if not observation:
                    observation = f"已删除资产 {asset_id} 并解除与剧本的关联。"
            except Exception as e:
                observation = observation or f"删除失败：{e}"

    elif action == "scan_text_assets":
        summary = AgentToolExecutor.scan_summary(store, script_id)
        if not observation:
            observation = summary

    elif action == "generate_images":
        items = data.get("items")
        added = 0
        prompt_ready = 0
        if isinstance(items, list) and items:
            for item in items:
                if not isinstance(item, dict):
                    continue
                source_id = item.get("source_text_asset_id")
                source_id_str = str(source_id) if source_id else None
                image_prompt = str(item.get("image_prompt", "")).strip()
                if source_id_str:
                    src = store.get_text_asset(source_id_str)
                    if src and is_image_text_asset(src.type):
                        content = normalize_image_text_content(src.type, src.content)
                        image_prompt = image_prompt or str(content.get("image_prompt", "")).strip()
                        if image_prompt:
                            prompt_ready += 1
                if item.get("media_id"):
                    added += 1
                    continue
                if persist_single_generated_image(store, ctx, item):
                    added += 1
        if not observation:
            if added:
                observation = f"已通过 Agnes AI 生成并落盘 {added} 张图片素材。"
            elif prompt_ready:
                from core.llm.tools.image.settings import is_image_gen_available

                if is_image_gen_available():
                    observation = (
                        f"生图 prompt 已就绪（{prompt_ready} 项），"
                        "Agnes AI 调用未返回有效图片，请检查 API Key 与网络。"
                    )
                else:
                    observation = (
                        f"生图 prompt 已就绪（{prompt_ready} 项），"
                        "请配置 SVG_IMAGE_GEN_API_KEY 或 AGNES_API_KEY 后重试。"
                    )
            else:
                observation = "无待生图项或未配置 Agnes 生图 API Key。"

    elif action == "load_context":
        assets = len(store.list_assets_for_script(script_id))
        count = int(data.get("asset_count", assets))
        if not observation:
            observation = f"已加载剧本上下文，关联资产 {count} 个。"

    elif action == "create_shots":
        shots = parse_shots_from_data(store, data.get("shots"))
        if not shots:
            raise ValueError("create_shots 未返回有效镜头列表")
        from core.edit.shot_validate import validate_shots_editable

        problems = validate_shots_editable(shots)
        if problems:
            first = next(iter(problems.values()))
            raise ValueError("分镜镜内结构校验失败：" + "；".join(first[:5]))
        style_mode = ctx.work_context.get("style_mode", VideoStyleMode.STORYBOOK)
        _assert_shots_have_voice_content(style_mode, shots, store=store, script_id=script_id)
        ctx.work_context["_pending_shots"] = shots
        if not observation:
            observation = f"已设计 {len(shots)} 个镜头。"

    elif action == "create_frames":
        pending = list(ctx.work_context.get("_pending_shots", []))
        if not pending:
            vp = store.get_video_plan_for_script(script_id)
            pending = list(vp.shots) if vp else []
        frames_data = data.get("frames")
        if not isinstance(frames_data, list) or not frames_data:
            raise ValueError("create_frames 未返回有效画面列表")
        created, updated_shots, frame_links = _create_frame_assets_from_data(
            store, ctx, frames_data, pending
        )
        if not created:
            raise ValueError("create_frames 未能关联到有效镜头")
        ctx.work_context["_pending_shots"] = updated_shots
        ctx.work_context["_frame_links"] = frame_links
        for asset in created:
            ctx.outputs.append(
                StepOutput(kind="text", label=asset.name, asset_id=asset.id)
            )
        if not observation:
            observation = f"已为 {len(created)} 个子镜创建剧本画面 frame 资产。"
            if frame_links:
                mapping = ", ".join(
                    f"{x['sub_shot_id'][:8]}→{x['frame_asset_id'][:8]}"
                    for x in frame_links[:6]
                )
                observation += f" 映射：{mapping}"

    elif action == "create_video_clips":
        pending = list(ctx.work_context.get("_pending_shots", []))
        if not pending:
            vp = store.get_video_plan_for_script(script_id)
            pending = list(vp.shots) if vp else []
        clips_data = data.get("video_clips")
        if not isinstance(clips_data, list) or not clips_data:
            raise ValueError("create_video_clips 未返回有效 video_clip 列表")
        created, updated_shots, clip_links = _create_video_clip_assets_from_data(
            store, ctx, clips_data, pending
        )
        if not created:
            raise ValueError("create_video_clips 未能关联到有效镜头")
        ctx.work_context["_pending_shots"] = updated_shots
        ctx.work_context["_video_clip_links"] = clip_links
        for asset in created:
            ctx.outputs.append(
                StepOutput(kind="text", label=asset.name, asset_id=asset.id)
            )
        if not observation:
            observation = f"已为 {len(created)} 个子镜创建 video_clip 文字资产。"
            if clip_links:
                mapping = ", ".join(
                    f"{x['sub_shot_id'][:8]}→{x['video_clip_asset_id'][:8]}"
                    for x in clip_links[:6]
                )
                observation += f" 映射：{mapping}"

    elif action == "persist_plan":
        shots = list(ctx.work_context.get("_pending_shots", []))
        if not shots:
            shots = parse_shots_from_data(store, data.get("shots"))
        if not shots:
            vp_existing = store.get_video_plan_for_script(script_id)
            shots = list(vp_existing.shots) if vp_existing else []
        else:
            shots = normalize_shot_orders(shots)
        style_mode = ctx.work_context.get("style_mode", VideoStyleMode.STORYBOOK)
        _assert_sub_shots_have_frames(style_mode, shots)
        _assert_sub_shots_have_video_clips(style_mode, shots)
        _assert_shots_have_voice_content(style_mode, shots)
        vp = VideoPlan(script_id=script_id, mode=style_mode, shots=shots)
        store.set_video_plan(vp)
        ctx.outputs.append(StepOutput(kind="json", label="video_plan", asset_id=vp.id))
        if not observation:
            observation = f"视频计划稿已保存，镜头数 {len(shots)}。"

    elif action == "load_shots":
        shot_count = AgentToolExecutor.load_shots_summary(store, script_id)
        shot_count = int(data.get("shot_count", shot_count or 3))
        ctx.work_context["_shot_count"] = shot_count
        if not observation:
            observation = f"已加载 {shot_count} 个镜头。"

    elif action == "generate_clips":
        clips = data.get("clips")
        added = 0
        timeline = store.get_edit_timeline_for_script(script_id)
        if (not isinstance(clips, list) or not clips) and timeline:
            for clip in flat_video_clips(timeline):
                if clip.asset_ref and clip.asset_ref in store.media_assets:
                    media = store.media_assets[clip.asset_ref]
                    if media.type.value == "video" and media.url:
                        clips = clips or []
                        clips.append(
                            {
                                "url": media.url,
                                "label": clip.label,
                                "asset_id": media.id,
                            }
                        )
        if isinstance(clips, list) and clips:
            for i, raw in enumerate(clips):
                if not isinstance(raw, dict):
                    continue
                url = str(raw.get("url", ""))
                if _is_placeholder_url(url):
                    continue
                vid_id = str(raw.get("asset_id", new_id("media")))
                label = str(raw.get("label", f"shot_{i}"))
                _persist_media(
                    store,
                    project_id=project_id,
                    script_id=script_id,
                    media_type=MediaAssetType.VIDEO,
                    name=label,
                    url=url,
                    asset_id=vid_id,
                )
                ctx.outputs.append(
                    StepOutput(
                        kind="video",
                        label=label,
                        asset_id=vid_id,
                        url=url,
                    )
                )
                shot_id = str(raw.get("shot_id", "")).strip()
                if shot_id:
                    from core.edit.shot_media_bind import bind_shot_video_media_to_plan

                    bind_shot_video_media_to_plan(store, script_id, shot_id, vid_id)
                added += 1
        if not observation:
            if added:
                observation = f"已记录 {added} 段视频片段。"
            else:
                from core.llm.tools.video.generate import is_video_gen_available

                if is_video_gen_available():
                    observation = "未生成有效视频片段，请确认镜头画面或提示词已就绪。"
                else:
                    observation = "视频生成未启用或缺少 API Key，已跳过媒体落盘。"

    elif action == "extract_narration":
        lines = int(data.get("line_count", 0))
        if not lines:
            vp = store.get_video_plan_for_script(script_id)
            lines = len(
                [
                    s
                    for s in (vp.shots if vp else [])
                    if any(c.text.strip() for t in s.audio_tracks for c in t.clips)
                ]
            )
        if not observation:
            observation = f"已提取 {lines} 条旁白文案。"

    elif action == "synthesize":
        from core.llm.tools.tts.synthesize import persist_single_synthesized_audio

        tracks = data.get("tracks")
        added = 0
        if isinstance(tracks, list):
            for raw in tracks:
                if not isinstance(raw, dict):
                    continue
                if persist_single_synthesized_audio(store, ctx, raw):
                    added += 1
        if not observation:
            if added:
                observation = f"已为 {added} 个镜头合成并落盘配音。"
            else:
                observation = "未生成有效配音资产。"

    elif action == "generate_from_timeline":
        timeline_id = str(data.get("timeline_id", "")).strip()
        timeline = (
            store.get_edit_timeline(timeline_id)
            if timeline_id
            else store.get_edit_timeline_for_script(script_id)
        )
        if timeline is None:
            if not observation:
                observation = "未找到剪辑计划稿，请先 plan_edit_timeline。"
        else:
            from core.llm.master.actions import uses_ai_video_pipeline

            style_mode = ctx.work_context.get("style_mode", VideoStyleMode.AI_VIDEO)
            if not uses_ai_video_pipeline(style_mode):
                if not observation:
                    observation = "storybook 模式请使用 editing_agent 合成，无需 video_agent。"
            else:
                synthetic_clips = []
                for clip in flat_video_clips(timeline):
                    synthetic_clips.append(
                        {
                            "label": clip.label or clip.id,
                            "shot_id": clip.metadata.get("shot_id", clip.id),
                            "url": str(data.get("placeholder_url", "")),
                        }
                    )
                data = {**data, "clips": synthetic_clips, "observation": observation}
                clips = data.get("clips")
                added = 0
                if isinstance(clips, list) and clips:
                    for i, raw in enumerate(clips):
                        if not isinstance(raw, dict):
                            continue
                        url = str(raw.get("url", ""))
                        if _is_placeholder_url(url):
                            continue
                        vid_id = str(raw.get("asset_id", new_id("media")))
                        label = str(raw.get("label", f"shot_{i}"))
                        _persist_media(
                            store,
                            project_id=project_id,
                            script_id=script_id,
                            media_type=MediaAssetType.VIDEO,
                            name=label,
                            url=url,
                            asset_id=vid_id,
                        )
                        ctx.outputs.append(
                            StepOutput(
                                kind="video",
                                label=label,
                                asset_id=vid_id,
                                url=url,
                            )
                        )
                        shot_id = str(raw.get("shot_id", "")).strip()
                        if shot_id:
                            from core.edit.shot_media_bind import (
                                bind_shot_video_media_to_plan,
                            )

                            bind_shot_video_media_to_plan(
                                store, script_id, shot_id, vid_id
                            )
                        added += 1
                if not observation:
                    if added:
                        observation = f"已按剪辑 video 轨记录 {added} 段视频片段。"
                    else:
                        from core.llm.tools.video.generate import is_video_gen_available

                        if is_video_gen_available():
                            observation = "未生成有效视频片段，请确认镜头画面或提示词已就绪。"
                        else:
                            observation = "视频生成未启用或缺少 API Key，已跳过媒体落盘。"

    elif action == "gather_media":
        timeline = store.get_edit_timeline_for_script(script_id)
        if timeline:
            from core.edit.compose import gather_timeline_media
            from core.edit.timeline import (
                build_timeline_layer_summary,
                format_layer_summary_text,
            )

            summary = gather_timeline_media(store, timeline)
            layer_summary = build_timeline_layer_summary(store, timeline)
            missing = summary.get("missing_refs") or []
            if not observation:
                observation = (
                    f"已收集剪辑素材：图片 {len(summary['images'])}、"
                    f"视频 {len(summary['videos'])}、配音 {len(summary['audios'])}，"
                    f"时长 {summary['duration_ms']}ms。"
                    f" {format_layer_summary_text(layer_summary)}。"
                )
            if missing:
                observation += f" 缺失引用：{', '.join(missing[:8])}。"
        elif not observation:
            observation = str(data.get("summary", "尚未生成剪辑计划稿，请先 plan_edit_timeline。"))

    elif action == "compose_final":
        from core.edit.asset_resolver import validate_edit_timeline
        from core.llm.hook.react_guard import EditComposeMissingAssetsError

        timeline_id = str(data.get("timeline_id", "")).strip()
        timeline = (
            store.get_edit_timeline(timeline_id)
            if timeline_id
            else store.get_edit_timeline_for_script(script_id)
        )
        style_mode = ctx.work_context.get("style_mode", VideoStyleMode.STORYBOOK)
        compose_plan = None
        if timeline:
            validation = validate_edit_timeline(store, timeline)
            if not validation.ready:
                raise EditComposeMissingAssetsError(
                    "compose_final",
                    f"成片合成前素材校验未通过，缺失 {len(validation.missing_items)} 项。",
                    validation_report=validation,
                )
            from core.edit.compose import compose_timeline_plan

            compose_plan = compose_timeline_plan(store, timeline, style_mode=style_mode)
            ctx.work_context["_compose_plan"] = compose_plan
        url = str(data.get("url", "") or data.get("final_url", ""))
        if url and not _is_placeholder_url(url):
            fin_id = str(data.get("asset_id", new_id("media")))
            label = str(data.get("label", "final_video"))
            _persist_media(
                store,
                project_id=project_id,
                script_id=script_id,
                media_type=MediaAssetType.FINAL,
                name=label,
                url=url,
                asset_id=fin_id,
            )
            ctx.outputs.append(
                StepOutput(
                    kind="video",
                    label=label,
                    asset_id=fin_id,
                    url=url,
                )
            )
            if not observation:
                observation = f"成片已合成，输出 {fin_id}。"
        elif compose_plan and compose_plan.get("segments"):
            from core.execution.cancel import check_cancelled

            check_cancelled(script_id)
            fin_id = str(data.get("asset_id", new_id("media")))
            label = str(data.get("label", "final_video"))
            if timeline and style_mode in (VideoStyleMode.STORYBOOK,):
                from core.edit.export_paths import export_filename_for_asset, prepare_export_output_path
                from core.edit.export_settings import get_export_manager
                from core.edit.ffmpeg_renderer import FfmpegExportError, export_timeline_to_mp4
                from core.store.project_paths import export_api_path

                export_mgr = get_export_manager()
                if not export_mgr.is_ffmpeg_export_enabled():
                    from core.edit.export_settings import CLASSIC_EXPORT_ONLY_MESSAGE

                    raise FfmpegExportError(CLASSIC_EXPORT_ONLY_MESSAGE)
                out_path = prepare_export_output_path(project_id, script_id, fin_id)
                export_name = export_filename_for_asset(fin_id)
                url = export_api_path(project_id, script_id, export_name)
                try:
                    skip_subtitles = bool(data.get("skip_subtitles"))
                    ffmpeg_result = export_timeline_to_mp4(
                        store,
                        timeline,
                        out_path,
                        project_id=project_id,
                        script_id=script_id,
                        style_mode=style_mode,
                        manager=export_mgr,
                        skip_subtitles=skip_subtitles,
                    )
                except FfmpegExportError as exc:
                    import json

                    from core.edit.timeline import build_timeline_layer_summary

                    layer_summary = build_timeline_layer_summary(store, timeline)
                    ctx.work_context["_last_compose_failure"] = {
                        "error": str(exc),
                        "layer_summary": layer_summary,
                    }
                    enriched = (
                        f"合成失败：{exc}\n\n【图层摘要】\n"
                        f"{json.dumps(layer_summary, ensure_ascii=False, indent=2)}"
                    )
                    logger.warning(
                        "FFmpeg compose_final failed script=%s: %s",
                        script_id,
                        exc,
                    )
                    raise FfmpegExportError(enriched) from exc
                _persist_media(
                    store,
                    project_id=project_id,
                    script_id=script_id,
                    media_type=MediaAssetType.FINAL,
                    name=label,
                    url=url,
                    asset_id=fin_id,
                    metadata={
                        "compose_plan": compose_plan,
                        "render": "ffmpeg",
                        "duration_ms": ffmpeg_result.duration_ms,
                        "segment_count": ffmpeg_result.segment_count,
                        "local_path": str(ffmpeg_result.output_path),
                    },
                )
                ctx.outputs.append(
                    StepOutput(
                        kind="video",
                        label=label,
                        asset_id=fin_id,
                        url=url,
                    )
                )
                if not observation:
                    observation = (
                        f"成片已通过 FFmpeg 合成，共 {ffmpeg_result.segment_count} 段，"
                        f"输出 {fin_id}。"
                    )
            else:
                meta_url = f"timeline://{timeline.id if timeline else 'draft'}"
                _persist_media(
                    store,
                    project_id=project_id,
                    script_id=script_id,
                    media_type=MediaAssetType.FINAL,
                    name=label,
                    url=meta_url,
                    asset_id=fin_id,
                    metadata={"compose_plan": compose_plan},
                )
                ctx.outputs.append(
                    StepOutput(
                        kind="video",
                        label=label,
                        asset_id=fin_id,
                        url=meta_url,
                    )
                )
                if not observation:
                    observation = (
                        f"剪辑计划已编译（{compose_plan['mode']}），"
                        f"共 {len(compose_plan['segments'])} 段；成片占位 {fin_id}。"
                    )
        elif not observation:
            observation = "剪辑合成 API 尚未接入，已跳过成片 URL 落盘。"

    else:
        if not observation:
            observation = f"已完成行动 {action}。"

    log_stage(logger, "agent.llm_action", action, agent=agent_name, step_id=ctx.step_id)
    return observation


async def run_llm_action(
    store: MemoryStore,
    llm_client: LLMClient,
    *,
    conversations: ConversationStore,
    agent_name: str,
    display_name: str,
    role_prompt: str,
    action: str,
    ctx: AgentRunContext,
    system_prompt: str | None = None,
    llm_config: LLMConfigManager | None = None,
) -> str:
    """调用 LLM 执行单个行动并应用结果。"""
    config = llm_config or LLMConfigManager()
    async with async_perf_span(
        "agent.llm_action",
        action,
        logger=logger,
        agent=agent_name,
        script_id=ctx.script_id,
        step_id=ctx.step_id,
    ):
        raw_chat = messages_to_chat_history(
            conversations.list_messages(ctx.conversation_id, "agent", agent_name),
            include_task=False,
        )
        action_context = build_action_user_content(
            store=store,
            role_prompt=role_prompt,
            display_name=display_name,
            action=action,
            task_brief="",
            observations=[] if raw_chat else (ctx.llm_observations or ctx.observations),
            completed_actions=ctx.completed_actions,
            work_context=ctx.work_context,
            history_summary="" if raw_chat else ctx.history_summary,
        )
        base_system = system_prompt or build_action_system_prompt(agent_name)
        turn_user = build_action_context_turn_content(action_context)
        estimate_prompt = (
            f"{base_system.rstrip()}\n\n{turn_user}" if turn_user else base_system
        )
        action_tools = [build_action_tool(agent_name, action)]
        log_ctx = {
            "project_id": ctx.work_context.get("project_id", ""),
            "script_id": ctx.script_id,
            "conversation_id": ctx.conversation_id,
            "agent_name": agent_name,
            "step_id": ctx.step_id,
            "role": "agent_action",
            "action": action,
        }
        chat_history = await prepare_react_chat_history(
            llm_client,
            config,
            messages=raw_chat,
            system_prompt=estimate_prompt,
            tools=action_tools,
            log_context=log_ctx,
            conversations=conversations,
            conversation_id=ctx.conversation_id,
            project_id=str(ctx.work_context.get("project_id", "")),
            script_id=ctx.script_id,
            channel="agent",
            agent_name=agent_name,
        )
        request = build_llm_request_ordered(
            system_prompt=base_system,
            tools=action_tools,
            anchor_user=ctx.task_brief,
            history=chat_history or None,
            turn_user=turn_user or None,
            tool_choice=tool_choice_force(action),
        )
        data = (
            await llm_client.complete_tool_calls(
                request,
                log_context=log_ctx,
                summary_prefix=f"动作 {action}",
            )
        ).primary_arguments()
        observation = apply_action_result(store, agent_name, action, ctx, data)
        immediate = action in (
            "compose_final",
            "create_shots",
            "create_frames",
            "create_video_clips",
            "persist_plan",
            "plan_edit_timeline",
            "build_edit_timeline",
            "generate_images",
            "search_images",
            "synthesize_narration",
            "synthesize_from_plan",
        ) or action.startswith(("create_", "update_", "delete_"))
        schedule_save(store, immediate=immediate)
        return observation
