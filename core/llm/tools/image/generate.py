"""generate_images：收集待生图项并并发调用 AI API。"""

from __future__ import annotations

import asyncio
import re

from typing import Any

from core.execution.cancel import ExecutionCancelledError, check_cancelled, gather_with_cancel
from core.llm.agent.react_core import AgentRunContext
from core.llm.hook.react_guard import ImageGenerationAbortError
from core.llm.tools.image.errors import (
    ImageGenFailureItem,
    build_failure_item,
    build_image_gen_failure_analysis,
    classify_image_gen_error,
    format_image_gen_abort_message,
    parse_agnes_api_error_body,
)
from core.assets.image_prompt import compose_base_image_prompt, compose_variant_image_prompt
from core.llm.tools.image.agnes_client import (
    AgnesImageGenerationError,
    generate_image_with_reference_async,
    generate_images_with_references_async,
    generate_text_to_image_async,
)
from core.llm.tools.image.sd_client import (
    SdImageGenerationError,
    download_reference_as_base64,
    sd_img2img,
    sd_txt2img,
)
from core.llm.tools.image.bailian_client import (
    BailianImageGenerationError,
    bailian_img2img,
    bailian_txt2img,
)
from core.llm.tools.image.reference_url import resolve_reference_url_for_media
from core.llm.tools.image.variants import collect_variant_generation_items
from core.llm.tools.image.frames import collect_frame_generation_items
from core.llm.tools.image.settings import (
    ImageGenSettings,
    get_image_gen_settings,
    is_image_gen_available,
)
from core.models.image_text_asset import (
    ImageVariant,
    find_variant as find_image_variant,
    get_base_variant,
    is_image_text_asset,
    normalize_image_text_content,
)
from core.store.memory import MemoryStore

IMAGE_GEN_MAX_ATTEMPTS = 3

# 提示词不合规时尝试去除的英文敏感词（使用 word boundary 匹配防止误伤）
_PROMPT_SENSITIVE_WORDS_EN = [
    "blood", "gore", "violence", "weapon", "nude", "naked",
    "kill", "murder", "dead", "death", "gun", "shooting",
    "hunt", "predator", "prey", "flesh", "carcass",
    "terror", "bomb", "explosive", "massacre",
]
_PROMPT_SENSITIVE_WORDS_CN = [
    "暴力", "血腥", "猎食", "捕食", "真实人物", "名人", "政治人物",
    "枪支", "武器", "裸露", "色情", "歧视", "种族", "恐怖",
]


def _sanitize_prompt_for_retry(prompt: str, error_category: str) -> str | None:
    """针对提示词不合规错误，去除敏感词后返回修改后的 prompt。
    仅当至少有一个词被修改时才返回新 prompt，否则返回 None（不重试）。
    如果清理后的 prompt 过短（少于 5 个字符），也不返回（无效）。"""
    if not prompt:
        return None
    modified = prompt
    changed = False
    # 英文词使用 word boundary 匹配防止误伤
    for word in _PROMPT_SENSITIVE_WORDS_EN:
        pattern = r"\b" + re.escape(word) + r"\b"
        new_text = re.sub(pattern, "", modified, flags=re.IGNORECASE)
        if new_text != modified:
            changed = True
            modified = new_text
    # 中文精确匹配
    for word in _PROMPT_SENSITIVE_WORDS_CN:
        if word in modified:
            modified = modified.replace(word, "")
            changed = True
    if not changed:
        return None
    # 清理多余空格和标点残留
    modified = re.sub(r"\s{2,}", " ", modified).strip()
    modified = re.sub(r",\s*,", ",", modified)
    modified = re.sub(r"\(\s*\)", "", modified)
    modified = re.sub(r"\[\s*\]", "", modified)
    modified = re.sub(r",(\S)", r", \1", modified)
    # 清理无意义的介词和连词残留
    modified = re.sub(r"\bwith\s+and\b", "with", modified, flags=re.IGNORECASE)
    modified = re.sub(r"\band\s+and\b", "and", modified, flags=re.IGNORECASE)
    modified = re.sub(r",\s*and\s*,", ",", modified)
    modified = re.sub(r"^\s*(and|with|of|or)\s+", "", modified, flags=re.IGNORECASE)
    modified = re.sub(r"\s+(and|with|of|or)\s*$", "", modified, flags=re.IGNORECASE)
    # 如果清理后的结果像 "A and range" 或 "a scene with everywhere"，尝试修复
    modified = re.sub(r"\bA and\b", "A", modified)
    modified = re.sub(r"\ba and\b", "a", modified)
    modified = re.sub(r"\bwith everywhere\b", "", modified, flags=re.IGNORECASE)
    modified = modified.strip()
    if len(modified) < 5:
        return None
    return modified


def _recompose_prompt_in_english(
    store: MemoryStore,
    item: dict[str, Any],
) -> str:
    """当使用本地 SD 时，重新组装纯英文提示词。

    委托给 sd_prompt_en.recompose_prompt_in_english()，
    该函数将中文 trait 标签、trait 值、颜色词等转为英文，
    移除无法翻译的中文内容，添加 SD 质量关键词。
    """
    from core.llm.tools.image.sd_prompt_en import recompose_prompt_in_english as _recompose

    return _recompose(store, item)


def _normalize_generation_item(
    store: MemoryStore,
    item: dict[str, Any],
) -> dict[str, Any] | None:
    source_id = str(item.get("source_text_asset_id", "")).strip()
    image_prompt = str(item.get("image_prompt", "")).strip()
    name = str(item.get("name", "")).strip()
    variant_id = str(item.get("variant_id", "")).strip()
    if source_id:
        src = store.get_text_asset(source_id)
        if src and is_image_text_asset(src.type):
            content = normalize_image_text_content(src.type, src.content)
            if variant_id:
                from core.models.image_text_asset import find_variant

                v = find_variant(content, variant_id)
                if v and str(v.image_prompt).strip():
                    image_prompt = str(v.image_prompt).strip()
            image_prompt = image_prompt or str(content.get("image_prompt", "")).strip()
            if not name:
                name = src.name
    if not source_id or not image_prompt:
        return None
    out = {
        "source_text_asset_id": source_id,
        "name": name or "image",
        "image_prompt": image_prompt,
        "asset_id": item.get("asset_id"),
        "url": str(item.get("url", "")).strip(),
    }
    if variant_id:
        out["variant_id"] = variant_id
        out["variant_kind"] = str(item.get("variant_kind", "")).strip()
    ref_mid = str(item.get("reference_media_id", "")).strip()
    ref_mids = item.get("reference_media_ids")
    if isinstance(ref_mids, list) and ref_mids:
        out["reference_media_ids"] = [str(m).strip() for m in ref_mids if str(m).strip()]
    elif ref_mid:
        out["reference_media_id"] = ref_mid
    asset_type = str(item.get("asset_type", "")).strip()
    if asset_type:
        out["asset_type"] = asset_type
    return out


def slim_generate_images_args(args: dict[str, Any]) -> dict[str, Any]:
    """
    LLM 常填入冗长 items（含 image_prompt）；后端 scan 补全，仅保留 source_text_asset_id。
    省略 items 时由 scan 自动收集全部待生图项。
    """
    out: dict[str, Any] = {}
    obs = str(args.get("observation", "")).strip()
    if obs:
        out["observation"] = obs
    raw_items = args.get("items")
    if isinstance(raw_items, list) and raw_items:
        slim: list[dict[str, str]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            sid = str(
                item.get("source_text_asset_id") or item.get("asset_id") or ""
            ).strip()
            vid = str(item.get("variant_id", "")).strip()
            if sid:
                entry: dict[str, str] = {"source_text_asset_id": sid}
                if vid:
                    entry["variant_id"] = vid
                slim.append(entry)
        if slim:
            out["items"] = slim
    for key in ("plan_status", "remaining_plan"):
        if key in args:
            out[key] = args[key]
    return out if out else dict(args)


def collect_generation_items(
    store: MemoryStore,
    script_id: str,
    args: dict[str, Any],
) -> list[dict[str, Any]]:
    """从 tool 参数或 scan 待生图列表收集生图任务。"""
    raw_items = args.get("items")
    filter_ids: set[str] | None = None
    if isinstance(raw_items, list) and raw_items:
        filter_ids = set()
        explicit_variants = False
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            sid = str(raw.get("source_text_asset_id", "")).strip()
            if sid:
                filter_ids.add(sid)
            if str(raw.get("variant_id", "")).strip():
                explicit_variants = True
        if explicit_variants:
            collected: list[dict[str, Any]] = []
            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue
                normalized = _normalize_generation_item(store, raw)
                if normalized:
                    collected.append(normalized)
            if collected:
                bases = [i for i in collected if i.get("variant_kind") == "base" or not i.get("reference_media_id")]
                derivs = [i for i in collected if i.get("reference_media_id")]
                return bases + derivs

    element_items = collect_variant_generation_items(
        store, script_id, asset_filter_ids=filter_ids if filter_ids else None
    )
    frame_items = collect_frame_generation_items(
        store, script_id, asset_filter_ids=filter_ids if filter_ids else None
    )
    return element_items + frame_items


def _is_skippable_url(url: str) -> bool:
    u = url.strip().lower()
    if not u:
        return True
    if "example.com" in u:
        return True
    if u.startswith("/assets/"):
        return True
    if u.startswith("placeholder:"):
        return True
    return False


async def _emit_image_gen_progress(ctx: AgentRunContext, **payload: Any) -> None:
    emitter = ctx.work_context.get("emitter")
    if emitter is None:
        return
    await emitter.emit(
        {
            "type": "image_gen_progress",
            "script_id": ctx.script_id,
            "step_id": ctx.step_id,
            **payload,
        }
    )


async def _emit_assets_changed(ctx: AgentRunContext) -> None:
    emitter = ctx.work_context.get("emitter")
    if emitter is None:
        return
    await emitter.emit(
        {
            "type": "assets_changed",
            "script_id": ctx.script_id,
            "agent_name": "image_agent",
            "action": "generate_images",
            "step_id": ctx.step_id,
        }
    )


async def _generate_one_item(
    store: MemoryStore,
    ctx: AgentRunContext,
    item: dict[str, Any],
    *,
    index: int,
    total: int,
    settings: ImageGenSettings,
    semaphore: asyncio.Semaphore,
) -> tuple[dict[str, Any] | None, ImageGenFailureItem | None]:
    from core.execution.cancel import check_cancelled
    from core.llm.agent.llm_action import persist_single_generated_image

    check_cancelled(ctx.script_id)

    source_id = item["source_text_asset_id"]
    name = item["name"]

    async with semaphore:
        await _emit_image_gen_progress(
            ctx,
            total=total,
            index=index,
            source_text_asset_id=source_id,
            name=name,
            status="started",
        )

        url = str(item.get("url", "")).strip()
        if url and not _is_skippable_url(url):
            media = persist_single_generated_image(store, ctx, item)
            result = dict(item)
            if media:
                result["media_id"] = media.id
                await _emit_assets_changed(ctx)
            from core.llm.tools.shared.media_list import resolve_media_access

            display_url = resolve_media_access(media.url)["link"] if media else url
            await _emit_image_gen_progress(
                ctx,
                total=total,
                index=index,
                source_text_asset_id=source_id,
                name=name,
                status="completed",
                url=display_url or url,
            )
            return result, None

        last_error = ""
        ref_mids = item.get("reference_media_ids")
        ref_mid = str(item.get("reference_media_id", "")).strip()
        is_sd = settings.provider == "local_sd"
        is_bailian = settings.provider == "bailian"

        # SD 生图时使用英文 trait 标签重新组装 prompt，提升生图质量
        image_prompt = item["image_prompt"]
        if is_sd:
            en_prompt = _recompose_prompt_in_english(store, item)
            if en_prompt:
                image_prompt = en_prompt

        for attempt in range(1, IMAGE_GEN_MAX_ATTEMPTS + 1):
            try:
                if is_bailian and isinstance(ref_mids, list) and ref_mids:
                    # 百炼多参考图融合合成（frame 画面生成）
                    ref_urls = [
                        resolve_reference_url_for_media(store, str(m))
                        for m in ref_mids
                    ]
                    image_url = await bailian_img2img(
                        image_prompt,
                        ref_urls,
                        settings=settings,
                    )
                elif is_bailian and ref_mid:
                    ref_url = resolve_reference_url_for_media(store, ref_mid)
                    image_url = await bailian_img2img(
                        image_prompt,
                        [ref_url],
                        settings=settings,
                    )
                elif is_bailian:
                    # 百炼纯文生图
                    image_url = await bailian_txt2img(
                        image_prompt,
                        settings=settings,
                    )
                elif is_sd and isinstance(ref_mids, list) and ref_mids:
                    # SD 多参考图：取第一张作为 init_image
                    ref_url = resolve_reference_url_for_media(store, str(ref_mids[0]))
                    init_b64 = await download_reference_as_base64(ref_url)
                    image_url = await sd_img2img(
                        image_prompt,
                        init_b64,
                        settings=settings,
                    )
                elif is_sd and ref_mid:
                    ref_url = resolve_reference_url_for_media(store, ref_mid)
                    init_b64 = await download_reference_as_base64(ref_url)
                    image_url = await sd_img2img(
                        image_prompt,
                        init_b64,
                        settings=settings,
                    )
                elif is_sd:
                    # SD 纯文生图
                    image_url = await sd_txt2img(
                        image_prompt,
                        settings=settings,
                    )
                elif isinstance(ref_mids, list) and ref_mids:
                    ref_urls = [
                        resolve_reference_url_for_media(store, str(m))
                        for m in ref_mids
                    ]
                    image_url = await generate_images_with_references_async(
                        item["image_prompt"],
                        ref_urls,
                        settings=settings,
                    )
                elif ref_mid:
                    ref_url = resolve_reference_url_for_media(store, ref_mid)
                    image_url = await generate_image_with_reference_async(
                        item["image_prompt"],
                        ref_url,
                        settings=settings,
                    )
                else:
                    image_url = await generate_text_to_image_async(
                        item["image_prompt"], settings=settings
                    )
            except (AgnesImageGenerationError, SdImageGenerationError, BailianImageGenerationError) as e:
                last_error = str(e)
                # 检查是否为提示词不合规错误，若是则尝试修改提示词后重试
                error_info = parse_agnes_api_error_body(
                    getattr(e, "http_status", 500) or 500,
                    str(e),
                )
                error_cat = classify_image_gen_error(
                    message=error_info.get("message", str(e)),
                    error_code=error_info.get("error_code", ""),
                    error_type=error_info.get("error_type", ""),
                    param=error_info.get("param", ""),
                    http_status=getattr(e, "http_status", None),
                )
                # 提示词类错误：修改 image_prompt 后重试
                if error_cat in ("content_policy", "invalid_prompt") and attempt < IMAGE_GEN_MAX_ATTEMPTS:
                    modified = _sanitize_prompt_for_retry(image_prompt, error_cat)
                    if modified and modified != image_prompt:
                        image_prompt = modified
                        item["image_prompt"] = modified
                if attempt < IMAGE_GEN_MAX_ATTEMPTS:
                    await _emit_image_gen_progress(
                        ctx,
                        total=total,
                        index=index,
                        source_text_asset_id=source_id,
                        name=name,
                        status="started",
                        attempt=attempt + 1,
                        max_attempts=IMAGE_GEN_MAX_ATTEMPTS,
                        error=last_error,
                    )
                    continue
                await _emit_image_gen_progress(
                    ctx,
                    total=total,
                    index=index,
                    source_text_asset_id=source_id,
                    name=name,
                    status="failed",
                    error=last_error,
                    attempts=IMAGE_GEN_MAX_ATTEMPTS,
                )
                return (
                    None,
                    build_failure_item(
                        source_text_asset_id=source_id,
                        asset_name=name,
                        image_prompt=item["image_prompt"],
                        error_message=last_error,
                        error_code=getattr(e, "error_code", ""),
                        error_type=getattr(e, "error_type", ""),
                        param=getattr(e, "param", ""),
                        http_status=getattr(e, "http_status", None),
                        attempts=IMAGE_GEN_MAX_ATTEMPTS,
                    ),
                )
            break

        enriched = {**item, "url": image_url}
        media = persist_single_generated_image(store, ctx, enriched)
        if media:
            enriched["media_id"] = media.id
            enriched["url"] = media.url
            await _emit_assets_changed(ctx)

        from core.llm.tools.shared.media_list import resolve_media_access

        display_url = resolve_media_access(media.url)["link"] if media else image_url
        await _emit_image_gen_progress(
            ctx,
            total=total,
            index=index,
            source_text_asset_id=source_id,
            name=name,
            status="completed",
            url=display_url or image_url,
        )
        return enriched, None


async def run_concurrent_image_generation(
    store: MemoryStore,
    script_id: str,
    args: dict[str, Any],
    ctx: AgentRunContext,
) -> tuple[dict[str, Any], list[str]]:
    """
    并发调用 Agnes API 生图，逐张落盘并通过 WS 推送 image_gen_progress。
    单项失败时最多重试 IMAGE_GEN_MAX_ATTEMPTS 次；仍有失败则抛出 ImageGenerationAbortError。
    """
    args = slim_generate_images_args(args)
    check_cancelled(ctx.script_id)
    if not is_image_gen_available():
        return args, []

    items = collect_generation_items(store, script_id, args)
    if not items:
        return args, []

    settings = get_image_gen_settings()
    frame_items = [i for i in items if i.get("reference_media_ids")]
    base_items = [
        i
        for i in items
        if i.get("variant_kind") == "base"
        or (not i.get("reference_media_id") and not i.get("reference_media_ids"))
    ]
    deriv_items = [
        i
        for i in items
        if i.get("reference_media_id")
        and not i.get("reference_media_ids")
        and i.get("variant_kind") != "base"
    ]

    generated: list[dict[str, Any]] = []
    failures: list[ImageGenFailureItem] = []

    async def _run_batch(batch: list[dict[str, Any]], start_index: int) -> None:
        nonlocal generated, failures
        if not batch:
            return
        total = len(batch)
        semaphore = asyncio.Semaphore(max(1, settings.max_concurrency))
        tasks = [
            _generate_one_item(
                store,
                ctx,
                item,
                index=start_index + idx,
                total=total,
                settings=settings,
                semaphore=semaphore,
            )
            for idx, item in enumerate(batch, start=1)
        ]
        results = await gather_with_cancel(ctx.script_id, tasks)
        for item_result, failure in results:
            if failure:
                failures.append(failure)
            if item_result:
                generated.append(item_result)

    await _run_batch(base_items, 1)
    if deriv_items and not failures:
        check_cancelled(ctx.script_id)
        await _run_batch(deriv_items, 1)
    if frame_items and not failures:
        check_cancelled(ctx.script_id)
        await _run_batch(frame_items, 1)

    total = len(items)

    if failures:
        analysis = build_image_gen_failure_analysis(
            failures,
            succeeded_count=len(generated),
            total_count=total,
        )
        raise ImageGenerationAbortError(
            "generate_images",
            format_image_gen_abort_message(analysis),
            failure_analysis=analysis,
        )

    if not generated:
        return args, []

    merged = dict(args)
    merged["items"] = generated
    return merged, []


async def enrich_generate_images_args(
    store: MemoryStore,
    script_id: str,
    args: dict[str, Any],
    ctx: AgentRunContext | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """为 generate_images 调用 Agnes API 并写入 items[].url（需 ctx 以推送进度）。"""
    if ctx is None:
        ctx = AgentRunContext(
            task_brief="",
            work_context={"script_id": script_id},
            script_id=script_id,
            step_id="",
            agent_name="image_agent",
        )
    return await run_concurrent_image_generation(store, script_id, args, ctx)
