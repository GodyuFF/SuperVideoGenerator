"""storyboard_agent load_context 结构化载荷。"""

from __future__ import annotations

from typing import Any

from core.llm.tools.image.scan import build_scan_text_assets_payload
from core.llm.tools.shared.linked_assets import (
    build_assets_with_images_from_scan,
    build_plots_for_script,
)
from core.store.memory import MemoryStore


def build_storyboard_context_payload(
    store: MemoryStore,
    script_id: str,
) -> dict[str, Any]:
    """剧本正文、剧情段落、图文资产与已链接图片，供分镜设计使用。"""
    script = store.get_script(script_id)
    if script is None:
        raise ValueError(f"剧本 {script_id} 不存在")

    payload = build_scan_text_assets_payload(store, script_id)
    script_block = dict(payload.get("script") or {})
    script_block["content_md"] = script.content_md or ""
    payload["script"] = script_block

    plots = build_plots_for_script(store, script_id)
    payload["plots"] = plots

    assets_with_images = build_assets_with_images_from_scan(payload.get("assets", []))
    payload["linked_image_count"] = len(assets_with_images)
    payload["assets_with_images"] = assets_with_images
    payload["plot_count"] = len(plots)
    return payload
