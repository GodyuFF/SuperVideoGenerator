"""关联资产动态提示词：生图/生视频时由 element_refs 展开，辅助模型理解主体。"""

from __future__ import annotations

from typing import Any

from core.assets.element_refs import DEFAULT_FRAME_REFERENCE_ORDER, normalize_element_refs
from core.store.memory import MemoryStore

_BUCKET_LABEL: dict[str, str] = {
    "scene": "空镜",
    "character": "角色",
    "prop": "物品",
    "frame": "画面",
    "video_clip": "视频片段",
}

_LINKED_BLOCK_HEADER = "【关联资产上下文】"
_LINKED_BLOCK_FOOTER = "生成时须保持上述主体外观、服装与场景氛围一致。"

_DEFAULT_VIDEO_ORDER: list[str] = [
    "scene",
    "character",
    "prop",
    "frame",
    "video_clip",
]


def _asset_brief(content: dict[str, Any], *, max_len: int = 180) -> str:
    """从关联资产 content 抽取短描述（优先 description / summary / 提示词）。"""
    for key in ("description", "summary", "image_prompt", "video_prompt"):
        val = str(content.get(key) or "").strip()
        if val:
            return val if len(val) <= max_len else val[: max_len - 1] + "…"
    return ""


def _character_traits_brief(content: dict[str, Any]) -> str:
    """角色扩展特征短摘，便于一致性约束。"""
    bits: list[str] = []
    for key in (
        "costume",
        "distinctive_features",
        "hair_style",
        "hair_color",
        "default_expression",
        "default_pose",
    ):
        val = str(content.get(key) or "").strip()
        if val and val != "未指定":
            bits.append(val)
    if not bits:
        return ""
    text = "、".join(bits[:4])
    return text if len(text) <= 120 else text[:119] + "…"


def build_linked_assets_aux_prompt(
    store: MemoryStore,
    content: dict[str, Any],
    *,
    reference_order: list[str] | None = None,
) -> str:
    """
    按 element_refs 动态生成关联资产辅助提示词。

    不修改存储中的 image_prompt / video_prompt；供生图/生视频调用时拼接。
    notes 不进入本辅助块。
    """
    refs = normalize_element_refs(content.get("element_refs"))
    if not refs:
        return ""

    order = list(reference_order or content.get("reference_order") or [])
    if not order:
        order = list(DEFAULT_FRAME_REFERENCE_ORDER)
    # 补全遗漏桶，避免漏引用
    for bucket in _DEFAULT_VIDEO_ORDER:
        if bucket not in order:
            order.append(bucket)

    lines: list[str] = [_LINKED_BLOCK_HEADER]
    for bucket in order:
        ids = refs.get(bucket) or []
        if not ids:
            continue
        label = _BUCKET_LABEL.get(bucket, bucket)
        for tid in ids:
            asset = store.get_text_asset(str(tid))
            if not asset:
                continue
            raw = asset.content if isinstance(asset.content, dict) else {}
            brief = _asset_brief(raw)
            if bucket == "character":
                traits = _character_traits_brief(raw)
                if traits:
                    brief = f"{brief}（{traits}）" if brief else traits
            name = (asset.name or asset.id).strip()
            if brief:
                lines.append(f"- {label}「{name}」：{brief}")
            else:
                lines.append(f"- {label}「{name}」")

    if len(lines) == 1:
        return ""
    lines.append(_LINKED_BLOCK_FOOTER)
    return "\n".join(lines)


def merge_prompt_with_linked_assets(
    base_prompt: str,
    store: MemoryStore | None,
    content: dict[str, Any],
    *,
    reference_order: list[str] | None = None,
) -> str:
    """
    将基础提示词与关联资产动态块合并。

    store 缺失或无引用时仅返回 base；已含关联块时不重复追加。
    """
    base = (base_prompt or "").strip()
    if store is None:
        return base
    if _LINKED_BLOCK_HEADER in base:
        return base
    aux = build_linked_assets_aux_prompt(
        store, content, reference_order=reference_order
    )
    if not aux:
        return base
    if not base:
        return aux
    return f"{base}\n\n{aux}"
