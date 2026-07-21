"""关联资产动态提示词：生图/生视频时由 element_refs 展开，标明第 N 张参考图。"""

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

# 桶 → 参考图用途说明（接在「——」后）
_BUCKET_ROLE: dict[str, str] = {
    "scene": "场景氛围参考",
    "character": "主体外观与服装参考",
    "prop": "道具外观参考",
    "frame": "画面构图参考",
    "video_clip": "动态参考",
}

_REF_BLOCK_HEADER = "【参考图说明】"
_POSITIVE_BLOCK_HEADER = "【正向提示词】"
_REF_BLOCK_FOOTER = "生成时须按参考图保持主体外观、服装与场景氛围一致。"

# 兼容检测：避免对已含新区的字符串重复合并
_LEGACY_BLOCK_HEADER = "【关联资产上下文】"

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


def _resolve_reference_order(
    content: dict[str, Any],
    reference_order: list[str] | None,
) -> list[str]:
    """解析参考遍历顺序：显式 order → content.reference_order → 默认，并补全遗漏桶。"""
    order = list(reference_order or content.get("reference_order") or [])
    if not order:
        order = list(DEFAULT_FRAME_REFERENCE_ORDER)
    for bucket in _DEFAULT_VIDEO_ORDER:
        if bucket not in order:
            order.append(bucket)
    return order


def build_linked_assets_aux_prompt(
    store: MemoryStore,
    content: dict[str, Any],
    *,
    reference_order: list[str] | None = None,
) -> str:
    """
    按 element_refs 生成【参考图说明】块（第 N 张图…）。

    序号与 reference_order 桶/桶内顺序一致，对齐 collect_reference_media_ids。
    不修改存储中的 image_prompt / video_prompt；notes 不进入本块。
    仅含条目行与标题，不含正向分区与页脚（由 merge 拼接）。
    """
    refs = normalize_element_refs(content.get("element_refs"))
    if not refs:
        return ""

    order = _resolve_reference_order(content, reference_order)
    lines: list[str] = [_REF_BLOCK_HEADER]
    index = 0
    for bucket in order:
        ids = refs.get(bucket) or []
        if not ids:
            continue
        label = _BUCKET_LABEL.get(bucket, bucket)
        role = _BUCKET_ROLE.get(bucket, "参考")
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
            index += 1
            head = f"第{index}张图：{label}「{name}」——{role}"
            if brief:
                lines.append(f"{head}。{brief}")
            else:
                lines.append(head)

    if index == 0:
        return ""
    return "\n".join(lines)


def merge_prompt_with_linked_assets(
    base_prompt: str,
    store: MemoryStore | None,
    content: dict[str, Any],
    *,
    reference_order: list[str] | None = None,
) -> str:
    """
    将基础正向提示词与【参考图说明】合并为实际生成全文。

    有参考块时：参考说明置顶 →【正向提示词】→ 页脚。
    无参考块时：原样返回 base（不加分区壳）。
    store 缺失时仅返回 base；已含参考说明头时不重复合并。
    """
    base = (base_prompt or "").strip()
    if store is None:
        return base
    if _REF_BLOCK_HEADER in base or _LEGACY_BLOCK_HEADER in base:
        return base
    aux = build_linked_assets_aux_prompt(
        store, content, reference_order=reference_order
    )
    if not aux:
        return base
    parts: list[str] = [aux]
    if base:
        parts.append(f"{_POSITIVE_BLOCK_HEADER}\n{base}")
    parts.append(_REF_BLOCK_FOOTER)
    return "\n\n".join(parts)
