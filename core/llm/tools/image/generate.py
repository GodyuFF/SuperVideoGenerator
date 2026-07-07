"""generate_images：收集待生图项并并发调用 Agnes AI API。"""

from __future__ import annotations

import asyncio
from typing import Any

from core.execution.cancel import ExecutionCancelledError, check_cancelled, gather_with_cancel
from core.llm.agent.react_core import AgentRunContext
from core.llm.hook.react_guard import ImageGenerationAbortError
from core.llm.tools.image.errors import (
    ImageGenFailureItem,
    build_failure_item,
    build_image_gen_failure_analysis,
    format_image_gen_abort_message,
)
from core.llm.tools.image.agnes_client import (
    AgnesImageGenerationError,
    generate_image_with_reference_async,
    generate_text_to_image_async,
)
from core.llm.tools.image.reference_url import resolve_reference_url_for_media
from core.llm.tools.image.variants import collect_variant_generation_items
from core.llm.tools.image.settings import (
    ImageGenSettings,
    get_image_gen_settings,
    is_image_gen_available,
)
from core.models.image_text_asset import is_image_text_asset, normalize_image_text_content
from core.store.memory import MemoryStore

IMAGE_GEN_MAX_ATTEMPTS = 3


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
    if ref_mid:
        out["reference_media_id"] = ref_mid
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

    return collect_variant_generation_items(
        store, script_id, asset_filter_ids=filter_ids if filter_ids else None
    )


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
        ref_mid = str(item.get("reference_media_id", "")).strip()
        for attempt in range(1, IMAGE_GEN_MAX_ATTEMPTS + 1):
            try:
                if ref_mid:
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
            except AgnesImageGenerationError as e:
                last_error = str(e)
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
    base_items = [i for i in items if i.get("variant_kind") == "base" or not i.get("reference_media_id")]
    deriv_items = [i for i in items if i.get("reference_media_id") and i.get("variant_kind") != "base"]

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
