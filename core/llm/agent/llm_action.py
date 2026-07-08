"""子 Agent 动作执行：通过 LLM 生成观察结果并落盘资产。"""

from typing import Any

from core.conversation import ConversationStore
from core.llm.agent.asset_content import extract_llm_content_field, normalize_asset_content
from core.llm.agent.react_core import AgentRunContext
from core.llm.client import LLMClient
from core.llm.tools_schema import build_action_tool, tool_choice_force
from core.llm.client.settings import LLMConfigManager
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
from core.llm.prompt.history_compress import (
    finalize_react_chat_history,
    maybe_compress_chat_history,
)
from core.llm.prompt.context_manager import AgentContextManager
from core.llm.prompt.registry import PromptProfile
from core.models.entities import (
    AssetReference,
    AssetScope,
    AssetStatus,
    MediaAsset,
    MediaAssetType,
    RelationType,
    StepOutput,
    TextAsset,
    TextAssetType,
    VideoPlan,
    VideoPlanShot,
    VideoStyleMode,
    normalize_shot_orders,
    new_id,
)
from core.store.memory import MemoryStore
from core.store.persist import schedule_save

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


def parse_shots_from_data(
    store: MemoryStore,
    shots_data: Any,
) -> list[VideoPlanShot]:
    shots: list[VideoPlanShot] = []
    if not isinstance(shots_data, list):
        return shots
    for i, raw in enumerate(shots_data):
        if not isinstance(raw, dict):
            continue
        narration = str(raw.get("narration_text", "")).strip()
        if not narration:
            continue
        refs = normalize_shot_asset_refs(raw.get("asset_refs") or {}, store)
        variant_refs_raw = raw.get("variant_refs")
        variant_refs: dict[str, str] = {}
        if isinstance(variant_refs_raw, dict):
            for k, v in variant_refs_raw.items():
                if k and v:
                    variant_refs[str(k)] = str(v)
        shots.append(
            VideoPlanShot(
                order=int(raw.get("order", i)),
                duration_ms=int(raw.get("duration_ms", 3000)),
                narration_text=narration,
                camera_motion=str(raw.get("camera_motion", "ken_burns_in")),
                asset_refs=refs,
                variant_refs=variant_refs,
            )
        )
    return normalize_shot_orders(shots) if shots else []


def _create_frame_assets_from_data(
    store: MemoryStore,
    ctx: AgentRunContext,
    frames_data: list[Any],
    pending_shots: list[VideoPlanShot],
) -> tuple[list[TextAsset], list[VideoPlanShot]]:
    from core.assets.service import finalize_text_asset_content_for_store
    from core.llm.agent.script_assets import link_script_asset

    script_id = ctx.script_id
    project_id = str(ctx.work_context.get("project_id", ""))
    if not project_id:
        script = store.get_script(script_id)
        project_id = script.project_id if script else ""

    shots_map = {s.id: s.model_copy() for s in pending_shots}
    shots_by_order = {s.order: s.id for s in pending_shots}
    created: list[TextAsset] = []

    for raw in frames_data:
        if not isinstance(raw, dict):
            continue
        shot_id = str(raw.get("shot_id", "")).strip()
        shot: VideoPlanShot | None = shots_map.get(shot_id) if shot_id else None
        if shot is None and raw.get("order") is not None:
            oid = shots_by_order.get(int(raw.get("order")))
            if oid:
                shot = shots_map.get(oid)
        if shot is None:
            continue

        element_refs_raw = raw.get("element_refs") or {}
        normalized_refs: dict[str, list[str]] = {}
        if isinstance(element_refs_raw, dict):
            for key in ("scene", "character", "prop"):
                val = element_refs_raw.get(key) or []
                ids = [str(v) for v in (val if isinstance(val, list) else [val]) if v]
                if ids:
                    normalized_refs[key] = ids

        if not normalized_refs:
            shot_refs = shot.asset_refs or {}
            for key in ("scene", "character", "prop"):
                ids = shot_refs.get(key) or []
                if ids:
                    normalized_refs[key] = [str(i) for i in ids]

        variant_refs: dict[str, str] = {}
        variant_refs_raw = raw.get("variant_refs")
        if isinstance(variant_refs_raw, dict):
            for k, v in variant_refs_raw.items():
                if k and v:
                    variant_refs[str(k)] = str(v)

        content: dict[str, Any] = {
            "description": str(raw.get("description", "")).strip(),
            "summary": str(raw.get("summary", "")).strip(),
            "element_refs": normalized_refs,
            "variant_refs": variant_refs,
            "shot_id": shot.id,
            "composition_prompt": str(raw.get("composition_prompt", "")).strip(),
            "reference_order": raw.get("reference_order")
            or ["scene", "character", "prop"],
        }
        name = str(raw.get("name", "")).strip() or f"画面·镜{shot.order + 1}"
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
        asset.content = finalize_text_asset_content_for_store(
            store, asset, content, force_recompose=True
        )
        store.add_text_asset(asset)
        link_script_asset(store, script_id, asset.id)
        created.append(asset)

        refs = dict(shot.asset_refs or {})
        refs["frame"] = [asset.id]
        shots_map[shot.id] = shot.model_copy(update={"asset_refs": refs})

    updated = normalize_shot_orders([shots_map[s.id] for s in pending_shots if s.id in shots_map])
    return created, updated


def build_action_system_prompt(
    agent_name: str,
    profile: PromptProfile = PromptProfile.DEFAULT,
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
    schedule_save(store, immediate=True)
    if source_id_str:
        src = store.get_text_asset(source_id_str)
        if src and src.type == TextAssetType.FRAME:
            src.primary_media_id = media.id
            store.update_text_asset(src)
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
            refs = ""
            if shot.asset_refs:
                refs = " refs=" + ",".join(
                    f"{k}:{','.join(v)}" for k, v in shot.asset_refs.items()
                )
            lines.append(
                f"  - 镜{shot.order + 1}: {shot.narration_text[:40]}…{refs}"
            )

    return "\n".join(lines) + ("\n" if lines else "")


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
        if script and data.get("title"):
            script.title = str(data["title"])
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
            if data.get("title"):
                script.title = str(data["title"])
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
        )
        ctx.outputs.append(StepOutput(kind="json", label="plot", asset_id=plot.id))
        if not observation:
            observation = f"已创建剧情资产 {plot.id}，并关联到剧本。"

    elif action == "create_character":
        character = create_text_asset_for_action(
            store,
            action=action,
            project_id=project_id,
            script_id=script_id,
            asset_name=str(data.get("asset_name", "主角")),
            content=extract_llm_content_field(data, action),
            observation=observation,
        )
        ctx.outputs.append(
            StepOutput(kind="json", label="character", asset_id=character.id)
        )
        if not observation:
            observation = f"已创建人物资产 {character.id}，并关联到剧本。"

    elif action == "create_scene":
        scene = create_text_asset_for_action(
            store,
            action=action,
            project_id=project_id,
            script_id=script_id,
            asset_name=str(data.get("asset_name", "场景")),
            content=extract_llm_content_field(data, action),
            observation=observation,
        )
        ctx.outputs.append(StepOutput(kind="json", label="scene", asset_id=scene.id))
        if not observation:
            observation = f"已创建场景资产 {scene.id}，并关联到剧本。"

    elif action == "create_prop":
        prop = create_text_asset_for_action(
            store,
            action=action,
            project_id=project_id,
            script_id=script_id,
            asset_name=str(data.get("asset_name", "道具")),
            content=extract_llm_content_field(data, action),
            observation=observation,
        )
        ctx.outputs.append(StepOutput(kind="json", label="prop", asset_id=prop.id))
        if not observation:
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
        by_type: dict[str, list[str]] = {}
        for a in store.list_assets_for_script(script_id):
            tv = a.type.value
            if tv in ("character", "scene", "prop"):
                by_type.setdefault(tv, []).append(a.id)
        if by_type:
            enriched: list[VideoPlanShot] = []
            for shot in shots:
                refs = dict(shot.asset_refs or {})
                if not refs:
                    for key in ("scene", "character", "prop"):
                        ids = by_type.get(key, [])
                        if ids:
                            refs[key] = ids[:1]
                enriched.append(shot.model_copy(update={"asset_refs": refs}))
            shots = enriched
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
        created, updated_shots = _create_frame_assets_from_data(
            store, ctx, frames_data, pending
        )
        if not created:
            raise ValueError("create_frames 未能关联到有效镜头")
        ctx.work_context["_pending_shots"] = updated_shots
        for asset in created:
            ctx.outputs.append(
                StepOutput(kind="text", label=asset.name, asset_id=asset.id)
            )
        if not observation:
            observation = f"已为 {len(created)} 个镜头创建画面资产。"

    elif action == "persist_plan":
        shots = list(ctx.work_context.get("_pending_shots", []))
        if not shots:
            shots = parse_shots_from_data(store, data.get("shots"))
        if not shots:
            vp_existing = store.get_video_plan_for_script(script_id)
            shots = list(vp_existing.shots) if vp_existing else []
        else:
            shots = normalize_shot_orders(shots)
        style_mode = ctx.work_context.get("style_mode", VideoStyleMode.DYNAMIC_IMAGE)
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
            for clip in timeline.tracks.get("video", []):
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
                added += 1
        if not observation:
            if added:
                observation = f"已记录 {added} 段视频片段。"
            else:
                observation = "视频生成 API 尚未接入，已跳过媒体 URL 落盘。"

    elif action == "extract_narration":
        lines = int(data.get("line_count", 0))
        if not lines:
            vp = store.get_video_plan_for_script(script_id)
            lines = len([s for s in (vp.shots if vp else []) if s.narration_text.strip()])
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
            style_mode = ctx.work_context.get("style_mode", VideoStyleMode.AI_VIDEO)
            if style_mode != VideoStyleMode.AI_VIDEO:
                if not observation:
                    observation = "dynamic_image 模式请使用 editing_agent 合成，无需 video_agent。"
            else:
                synthetic_clips = []
                for clip in timeline.tracks.get("video", []):
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
                        added += 1
                if not observation:
                    if added:
                        observation = f"已按剪辑 video 轨记录 {added} 段视频片段。"
                    else:
                        observation = "视频生成 API 尚未接入，已跳过 media URL 落盘。"

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
        style_mode = ctx.work_context.get("style_mode", VideoStyleMode.DYNAMIC_IMAGE)
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
            if timeline and style_mode in (
                VideoStyleMode.DYNAMIC_IMAGE,
                VideoStyleMode.DYNAMIC_COMIC,
            ):
                from core.edit.export_paths import export_filename_for_asset, prepare_export_output_path
                from core.edit.export_settings import get_export_manager
                from core.edit.ffmpeg_renderer import FfmpegExportError, export_timeline_to_mp4
                from core.store.project_paths import export_api_path

                export_mgr = get_export_manager()
                if not export_mgr.get_settings().enabled:
                    raise FfmpegExportError("FFmpeg 导出未启用")
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
    compressed = await maybe_compress_chat_history(
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
    chat_history = await finalize_react_chat_history(compressed)
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
