"""资产详情页二次生成：统一分发至生图 / TTS / 视频流水线。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from core.edit.storyboard_restructure import invalidate_shot_tts
from core.events.emitter import EventEmitter
from core.guards.reference import ScriptEditGuard, ScriptEditGuardError
from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.image.generate import (
    build_regeneration_generation_items,
    run_concurrent_image_generation,
)
from core.llm.tools.image.settings import is_image_gen_available
from core.llm.tools.tts.handler import handle_synthesize
from core.llm.tools.video.settings import get_video_gen_manager
from core.models.entities import MediaAsset, MediaAssetType, Script, ScriptStatus, TextAsset, TextAssetType
from core.models.image_text_asset import is_image_text_asset, normalize_image_text_content
from core.models.video_text_asset import is_video_text_asset
from core.store.memory import MemoryStore
from core.store.persist import schedule_save

ShotRegenerateKind = Literal["tts", "frame", "video"]
GenerationQueueKind = Literal["image", "video"]


@dataclass
class VideoRegenerateOptions:
    """分镜 AI 视频二次生成可选参考源（画面 / 图片 / 元素引用）。"""

    sub_shot_idx: int = 0
    source_frame_asset_ids: list[str] = field(default_factory=list)
    source_media_ids: list[str] = field(default_factory=list)
    source_element_refs: dict[str, list[str]] = field(default_factory=dict)
    source_video_clip_asset_ids: list[str] = field(default_factory=list)
    video_mode: str | None = None

    @classmethod
    def from_payload(cls, raw: dict[str, Any] | None) -> VideoRegenerateOptions | None:
        """从 API JSON 解析视频生成选项。"""
        if not raw or not isinstance(raw, dict):
            return None
        frames = raw.get("source_frame_asset_ids") or []
        media = raw.get("source_media_ids") or []
        refs = raw.get("source_element_refs") or {}
        vc_ids = raw.get("source_video_clip_asset_ids") or []
        if not isinstance(frames, list):
            frames = []
        if not isinstance(media, list):
            media = []
        if not isinstance(vc_ids, list):
            vc_ids = []
        if not isinstance(refs, dict):
            refs = {}
        cleaned_refs: dict[str, list[str]] = {}
        for bucket in ("scene", "character", "prop", "frame"):
            val = refs.get(bucket)
            if val is None:
                continue
            ids = val if isinstance(val, list) else [val]
            cleaned = [str(x).strip() for x in ids if str(x).strip()]
            if cleaned:
                cleaned_refs[bucket] = cleaned
        mode = str(raw.get("video_mode") or "").strip() or None
        return cls(
            sub_shot_idx=int(raw.get("sub_shot_idx") or 0),
            source_frame_asset_ids=[str(x).strip() for x in frames if str(x).strip()],
            source_media_ids=[str(x).strip() for x in media if str(x).strip()],
            source_element_refs=cleaned_refs,
            source_video_clip_asset_ids=[str(x).strip() for x in vc_ids if str(x).strip()],
            video_mode=mode,
        )

    def has_explicit_sources(self) -> bool:
        """是否指定了至少一类参考源。"""
        if self.source_frame_asset_ids or self.source_media_ids:
            return True
        return any(bool(v) for v in self.source_element_refs.values())

    def to_generate_args(self) -> dict[str, Any]:
        """转为 generate_clips 参数字段。"""
        out: dict[str, Any] = {"sub_shot_idx": self.sub_shot_idx}
        if self.source_frame_asset_ids:
            out["source_frame_asset_ids"] = list(self.source_frame_asset_ids)
        if self.source_media_ids:
            out["source_media_ids"] = list(self.source_media_ids)
        if self.source_element_refs:
            out["source_element_refs"] = dict(self.source_element_refs)
        if self.source_video_clip_asset_ids:
            out["video_clip_asset_ids"] = list(self.source_video_clip_asset_ids)
        if self.video_mode:
            out["video_mode"] = self.video_mode
        return out


class RegenerateError(Exception):
    """二次生成失败基类。"""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        self.status_code = status_code
        super().__init__(message)


class RegenerateNotFoundError(RegenerateError):
    """资产或镜头不存在。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=404)


class RegenerateNotAllowedError(RegenerateError):
    """当前剧本状态不允许二次生成。"""

    def __init__(self, message: str, *, status_code: int = 403) -> None:
        super().__init__(message, status_code=status_code)


class RegenerateNotAvailableError(RegenerateError):
    """生图/TTS/视频服务未配置或不可用。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=503)


@dataclass
class RegenerateResult:
    """单资产或分镜级二次生成结果。"""

    ok: bool
    kind: str
    job_id: str
    asset_id: str
    asset_ids: list[str] = field(default_factory=list)
    message: str = ""


def _utc_now_iso() -> str:
    """返回当前 UTC ISO 时间戳。"""
    return datetime.now(timezone.utc).isoformat()


def infer_generation_queue_kind(
    store: MemoryStore,
    asset_id: str,
) -> GenerationQueueKind | None:
    """判断单资产二次生成是否应入队（image/video），TTS 等返回 None 直跑。"""
    text_asset = store.get_text_asset(asset_id)
    if text_asset is not None:
        if text_asset.type == TextAssetType.VIDEO_CLIP:
            return "video"
        if is_image_text_asset(text_asset.type):
            return "image"
        return None

    media = store.media_assets.get(asset_id)
    if media is None:
        return None
    if media.type == MediaAssetType.IMAGE:
        return "image"
    if media.type == MediaAssetType.VIDEO:
        return "video"
    return None


def asset_label_for_queue(store: MemoryStore, asset_id: str) -> str:
    """解析资产展示名，供生成队列入队标签使用。"""
    text_asset = store.get_text_asset(asset_id)
    if text_asset is not None:
        return text_asset.name or asset_id
    media = store.media_assets.get(asset_id)
    if media is not None:
        return media.name or asset_id
    return asset_id


def mark_media_superseded(store: MemoryStore, media_id: str) -> None:
    """将指定媒体资产标记为已被新版本取代。"""
    media = store.media_assets.get(media_id)
    if not media:
        return
    meta = dict(media.metadata or {})
    if meta.get("superseded"):
        return
    meta["superseded"] = True
    meta["superseded_at"] = _utc_now_iso()
    media.metadata = meta


def mark_text_asset_linked_media_superseded(
    store: MemoryStore,
    text_asset_id: str,
    *,
    variant_id: str | None = None,
) -> None:
    """将文字资产关联的未 superseded 图片媒体标记为旧版。"""
    for media in store.media_assets.values():
        if media.type != MediaAssetType.IMAGE:
            continue
        meta = media.metadata or {}
        if meta.get("superseded"):
            continue
        source_id = str(media.source_asset_id or meta.get("source_text_asset_id") or "")
        if source_id != text_asset_id:
            continue
        if variant_id:
            if str(meta.get("variant_id") or "") != variant_id:
                continue
        mark_media_superseded(store, media.id)


def mark_shot_video_superseded(store: MemoryStore, script_id: str, shot_id: str) -> None:
    """将镜头关联的视频媒体标记为 superseded。"""
    for media in store.media_assets.values():
        if media.type != MediaAssetType.VIDEO:
            continue
        meta = media.metadata or {}
        if meta.get("superseded"):
            continue
        if str(meta.get("shot_id") or "") == shot_id and (media.script_id or "") == script_id:
            mark_media_superseded(store, media.id)


def assert_regenerate_allowed(
    store: MemoryStore,
    script: Script,
    *,
    master_active: bool = False,
) -> None:
    """校验剧本是否允许发起详情页二次生成。"""
    if script.status == ScriptStatus.EXECUTING:
        raise RegenerateNotAllowedError(
            f"剧本 {script.id} 正在执行中，请等待完成后再二次生成",
            status_code=403,
        )
    if master_active:
        raise RegenerateNotAllowedError(
            "主编排任务进行中，请稍后再试",
            status_code=409,
        )
    try:
        ScriptEditGuard.assert_editable(script)
    except ScriptEditGuardError as exc:
        raise RegenerateNotAllowedError(str(exc), status_code=403) from exc


def build_regenerate_context(
    *,
    store: MemoryStore,
    emitter: EventEmitter | None,
    project_id: str,
    script_id: str,
    agent_name: str = "regenerate",
) -> AgentRunContext:
    """构造最小 AgentRunContext，复用生图/TTS 进度推送。"""
    work_context: dict[str, Any] = {
        "project_id": project_id,
        "script_id": script_id,
    }
    if emitter is not None:
        work_context["emitter"] = emitter
    return AgentRunContext(
        task_brief="详情页二次生成",
        work_context=work_context,
        script_id=script_id,
        step_id=f"regen_{uuid.uuid4().hex[:8]}",
        agent_name=agent_name,
        project_id=project_id,
    )


async def _emit_assets_changed(
    emitter: EventEmitter | None,
    script_id: str,
    *,
    action: str,
    asset_id: str | None = None,
) -> None:
    """二次生成完成后通知前端刷新看板。"""
    if emitter is None:
        return
    payload: dict[str, Any] = {
        "type": "assets_changed",
        "script_id": script_id,
        "action": action,
        "agent_name": "regenerate",
    }
    if asset_id:
        payload["asset_id"] = asset_id
    await emitter.emit(payload)


def _raise_regenerate_image_item_error(
    store: MemoryStore,
    text_asset: TextAsset,
) -> None:
    """二次生成无法组装任务时抛出可读错误。"""
    from core.assets.image_prompt import compose_base_image_prompt, compose_frame_image_prompt
    from core.llm.tools.image.frames import collect_reference_media_ids
    from core.models.entities import TextAssetType

    content = normalize_image_text_content(text_asset.type, text_asset.content)
    if text_asset.type == TextAssetType.FRAME:
        _, refs_ready, pending_reason = collect_reference_media_ids(store, content)
        if not refs_ready:
            detail = pending_reason or "请先在关联资产中完成角色/空镜/物品的生图"
            raise RegenerateError(f"画面参考图未就绪，无法重新生图：{detail}")
    prompt = str(content.get("image_prompt", "")).strip()
    if not prompt:
        if text_asset.type == TextAssetType.FRAME:
            prompt, _ = compose_frame_image_prompt(content, store=store)
        else:
            prompt, _ = compose_base_image_prompt(text_asset.type, content)
    if not prompt:
        raise RegenerateError(
            "未找到可生图的任务项，请填写主视觉描述或生图 Prompt 后点击保存，再重新生成。"
        )
    raise RegenerateError("未找到可生图的任务项，请确认资产已填写 image_prompt。")


async def _regenerate_text_asset_images(
    store: MemoryStore,
    ctx: AgentRunContext,
    text_asset: TextAsset,
    *,
    variant_id: str | None = None,
) -> RegenerateResult:
    """对图文文字资产重新生图。"""
    if not is_image_gen_available():
        raise RegenerateNotAvailableError("生图服务未启用或缺少 API Key，请在 AI 设置中配置。")

    mark_text_asset_linked_media_superseded(store, text_asset.id, variant_id=variant_id)
    forced_items = build_regeneration_generation_items(
        store,
        ctx.script_id,
        text_asset.id,
        variant_id=variant_id,
    )
    if not forced_items:
        _raise_regenerate_image_item_error(store, text_asset)

    slim_item: dict[str, str] = {"source_text_asset_id": text_asset.id}
    if variant_id:
        slim_item["variant_id"] = variant_id
    args = {
        "observation": f"二次生成 {text_asset.name} 图片",
        "items": [slim_item],
        "_forced_generation_items": forced_items,
    }

    enriched, _ = await run_concurrent_image_generation(store, ctx.script_id, args, ctx)
    generated = enriched.get("items") or []
    new_ids = [
        str(g.get("media_id") or g.get("asset_id") or "")
        for g in generated
        if isinstance(g, dict)
    ]
    new_ids = [i for i in new_ids if i]
    schedule_save(store, immediate=True)
    emitter = ctx.work_context.get("emitter")
    if isinstance(emitter, EventEmitter):
        await _emit_assets_changed(emitter, ctx.script_id, action="regenerate_image", asset_id=text_asset.id)

    primary = new_ids[0] if new_ids else text_asset.id
    return RegenerateResult(
        ok=bool(new_ids),
        kind="image",
        job_id=ctx.step_id,
        asset_id=primary,
        asset_ids=new_ids,
        message=f"已为「{text_asset.name}」重新生成 {len(new_ids)} 张图片",
    )


async def _regenerate_media_image(
    store: MemoryStore,
    ctx: AgentRunContext,
    media: MediaAsset,
) -> RegenerateResult:
    """对图片数字资产从其来源文字资产重新生图。"""
    source_id = str(media.source_asset_id or (media.metadata or {}).get("source_text_asset_id") or "")
    if not source_id:
        raise RegenerateError("该图片缺少来源文字资产，无法二次生成。")
    text_asset = store.get_text_asset(source_id)
    if not text_asset:
        raise RegenerateNotFoundError(f"来源文字资产 {source_id} 不存在")
    variant_id = str((media.metadata or {}).get("variant_id") or "") or None
    mark_media_superseded(store, media.id)
    return await _regenerate_text_asset_images(
        store, ctx, text_asset, variant_id=variant_id
    )


async def _regenerate_media_tts(
    store: MemoryStore,
    ctx: AgentRunContext,
    media: MediaAsset,
) -> RegenerateResult:
    """对配音数字资产按镜头重新合成 TTS。"""
    shot_id = str((media.metadata or {}).get("shot_id") or "")
    if not shot_id:
        raise RegenerateError("该配音缺少 shot_id，无法二次生成。")
    mark_media_superseded(store, media.id)
    return await _regenerate_shot_tts(store, ctx, shot_id)


async def _regenerate_media_video(
    store: MemoryStore,
    ctx: AgentRunContext,
    media: MediaAsset,
) -> RegenerateResult:
    """对视频数字资产按镜头重新生成（需视频 API 已配置）。"""
    shot_id = str((media.metadata or {}).get("shot_id") or "")
    if not shot_id:
        raise RegenerateError("该视频缺少 shot_id，无法二次生成。")
    mark_media_superseded(store, media.id)
    return await _regenerate_shot_video(store, ctx, shot_id)


async def _regenerate_shot_tts(
    store: MemoryStore,
    ctx: AgentRunContext,
    shot_id: str,
) -> RegenerateResult:
    """为单个镜头重新合成配音。"""
    from core.llm.tools.tts.settings import get_tts_manager
    from core.tts.engine import build_runtime_config, is_tts_available

    manager = get_tts_manager()
    settings = manager.get_settings()
    runtime = build_runtime_config(settings, manager.resolved_api_key())
    if not is_tts_available(runtime):
        raise RegenerateNotAvailableError("TTS 未启用或缺少必要配置，请在 AI 设置中配置。")

    invalidate_shot_tts(store, ctx.script_id, shot_id)
    args = {
        "observation": f"二次生成镜头 {shot_id} 配音",
        "shot_ids": [shot_id],
    }
    result = await handle_synthesize(store, ctx, args)
    if not result.ok:
        raise RegenerateError(result.observation or "配音二次生成失败")

    new_ids = [
        str(o.asset_id)
        for o in (result.outputs or [])
        if o.asset_id
    ]
    schedule_save(store, immediate=True)
    emitter = ctx.work_context.get("emitter")
    if isinstance(emitter, EventEmitter):
        await _emit_assets_changed(emitter, ctx.script_id, action="regenerate_tts", asset_id=shot_id)

    return RegenerateResult(
        ok=True,
        kind="tts",
        job_id=ctx.step_id,
        asset_id=new_ids[0] if new_ids else shot_id,
        asset_ids=new_ids,
        message=f"已为镜头 {shot_id} 重新合成配音",
    )


async def _regenerate_shot_video(
    store: MemoryStore,
    ctx: AgentRunContext,
    shot_id: str,
    *,
    video_options: VideoRegenerateOptions | None = None,
) -> RegenerateResult:
    """为单个镜头重新生成 AI 视频片段。"""
    from core.llm.tools.video.handler import handle_generate_clips
    from core.llm.style.video_capability import script_style_video_modes

    video_mgr = get_video_gen_manager()
    if not video_mgr.is_available():
        raise RegenerateNotAvailableError(
            "AI 视频生成未启用或缺少 API Key，请在 AI 设置中启用 SVG_VIDEO_GEN 后重试。"
        )

    if not script_style_video_modes(store, ctx.script_id):
        raise RegenerateNotAllowedError(
            "当前视频风格未配置 AI 生视频能力（video），无法二次生成视频。"
        )

    mark_shot_video_superseded(store, ctx.script_id, shot_id)
    plan = store.get_video_plan_for_script(ctx.script_id)
    if not plan:
        raise RegenerateError("未找到视频计划稿，无法生成 AI 视频。")
    shot = next((s for s in plan.shots if s.id == shot_id), None)
    if not shot:
        raise RegenerateNotFoundError(f"镜头 {shot_id} 不存在")

    args: dict[str, Any] = {
        "observation": f"二次生成镜头 {shot_id} 视频",
        "shot_ids": [shot_id],
    }
    if video_options:
        args.update(video_options.to_generate_args())
    result = await handle_generate_clips(store, ctx, args)
    if not result.ok:
        raise RegenerateError(result.observation or "视频二次生成失败")

    new_ids = [
        str(o.asset_id)
        for o in (result.outputs or [])
        if o.asset_id
    ]
    schedule_save(store, immediate=True)
    emitter = ctx.work_context.get("emitter")
    if isinstance(emitter, EventEmitter):
        await _emit_assets_changed(
            emitter, ctx.script_id, action="regenerate_video", asset_id=shot_id
        )

    return RegenerateResult(
        ok=True,
        kind="video",
        job_id=ctx.step_id,
        asset_id=new_ids[0] if new_ids else shot_id,
        asset_ids=new_ids,
        message=f"已为镜头 {shot_id} 重新生成 AI 视频",
    )


def _resolve_shot_frame_asset_id(store: MemoryStore, script_id: str, shot_id: str) -> str | None:
    """从镜内子镜 images[].frame_asset_id 解析 frame 文字资产 ID。"""
    plan = store.get_video_plan_for_script(script_id)
    if not plan:
        return None
    shot = next((s for s in plan.shots if s.id == shot_id), None)
    if not shot:
        return None
    for sub in shot.sub_shots:
        for img in sub.images:
            if img.frame_asset_id:
                return img.frame_asset_id.strip() or None
    return None


def _resolve_shot_video_clip_asset_id(
    store: MemoryStore,
    script_id: str,
    shot_id: str,
) -> str | None:
    """从镜内子镜 videos[].video_clip_asset_id 解析 video_clip 文字资产 ID。"""
    plan = store.get_video_plan_for_script(script_id)
    if not plan:
        return None
    shot = next((s for s in plan.shots if s.id == shot_id), None)
    if not shot:
        return None
    for sub in shot.sub_shots:
        for vid in sub.videos:
            clip_id = str(getattr(vid, "video_clip_asset_id", "") or "").strip()
            if clip_id and store.get_text_asset(clip_id):
                return clip_id
    return None


def build_shot_video_enqueue_payload(
    shot_id: str,
    *,
    video_options: VideoRegenerateOptions | None = None,
) -> dict[str, Any]:
    """构造分镜级 AI 视频二次生成队列入队载荷（无 video_clip 资产时）。"""
    payload: dict[str, Any] = {
        "regenerate_shot_video": True,
        "shot_id": shot_id,
    }
    if video_options is not None:
        payload.update(video_options.to_generate_args())
    return payload


async def _regenerate_video_clip(
    store: MemoryStore,
    ctx: AgentRunContext,
    text_asset: TextAsset,
) -> RegenerateResult:
    """对 video_clip 文字资产重新生成 AI 视频。"""
    from core.llm.tools.video.handler import handle_generate_video_clips
    from core.llm.style.video_capability import script_style_video_modes

    if not get_video_gen_manager().is_available():
        raise RegenerateNotAvailableError(
            "AI 视频生成未启用或缺少 API Key，请在 AI 设置中启用 SVG_VIDEO_GEN 后重试。"
        )
    if not script_style_video_modes(store, ctx.script_id):
        raise RegenerateNotAllowedError(
            "当前视频风格未配置 AI 生视频能力（video），无法二次生成视频。"
        )
    for mid in [
        m.id
        for m in store.media_assets.values()
        if m.source_asset_id == text_asset.id
    ]:
        mark_media_superseded(store, mid)
    args = {
        "observation": f"二次生成 video_clip {text_asset.name}",
        "asset_ids": [text_asset.id],
    }
    result = await handle_generate_video_clips(store, ctx, args)
    if not result.ok:
        raise RegenerateError(result.observation or "video_clip 二次生成失败")
    new_ids = [
        str(o.asset_id) for o in (result.outputs or []) if o.asset_id
    ]
    schedule_save(store, immediate=True)
    emitter = ctx.work_context.get("emitter")
    if isinstance(emitter, EventEmitter):
        await _emit_assets_changed(
            emitter, ctx.script_id, action="regenerate_video", asset_id=text_asset.id
        )
    return RegenerateResult(
        ok=True,
        kind="video",
        job_id=ctx.step_id,
        asset_id=new_ids[0] if new_ids else text_asset.id,
        asset_ids=new_ids,
        message=f"已为「{text_asset.name}」重新生成视频",
    )


async def regenerate_asset(
    store: MemoryStore,
    emitter: EventEmitter | None,
    *,
    project_id: str,
    script_id: str,
    asset_id: str,
    variant_id: str | None = None,
    master_active: bool = False,
) -> RegenerateResult:
    """单资产二次生成入口：按类型分发至生图/TTS/视频流水线。"""
    script = store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise RegenerateNotFoundError("剧本不存在")
    assert_regenerate_allowed(store, script, master_active=master_active)

    ctx = build_regenerate_context(
        store=store,
        emitter=emitter,
        project_id=project_id,
        script_id=script_id,
    )

    text_asset = store.get_text_asset(asset_id)
    if text_asset:
        if text_asset.type == TextAssetType.VIDEO_CLIP:
            return await _regenerate_video_clip(store, ctx, text_asset)
        if not is_image_text_asset(text_asset.type):
            raise RegenerateError(f"文字资产类型 {text_asset.type} 不支持二次生成。")
        return await _regenerate_text_asset_images(
            store, ctx, text_asset, variant_id=variant_id
        )

    media = store.media_assets.get(asset_id)
    if not media or media.project_id != project_id:
        raise RegenerateNotFoundError(f"资产 {asset_id} 不存在")

    if media.type == MediaAssetType.IMAGE:
        return await _regenerate_media_image(store, ctx, media)
    if media.type == MediaAssetType.AUDIO:
        return await _regenerate_media_tts(store, ctx, media)
    if media.type == MediaAssetType.VIDEO:
        return await _regenerate_media_video(store, ctx, media)

    raise RegenerateError(f"媒体类型 {media.type} 不支持二次生成。")
