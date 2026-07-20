"""分镜复核 Agent 已废弃 action 名 → 现行 canonical tool 映射。"""

from __future__ import annotations

# 清理历史兼容逻辑后，LLM 仍可能从旧对话/旧 prompt 记忆调用左侧名称。
REFINE_LEGACY_ACTION_ALIASES: dict[str, str] = {
    "load_review_context": "get_shot_details",
    "load_refine_context": "get_refine_plan",
    "sync_from_tts": "sync_actual_assets",
    "refine_shots": "review_and_restructure",
    "persist_shot_detail": "persist_review",
}


def resolve_refine_action_alias(action: str) -> str:
    """将 storyboard_refine 废弃 action 名解析为现行 Registry tool 名。"""
    key = str(action or "").strip()
    if not key:
        return key
    return REFINE_LEGACY_ACTION_ALIASES.get(key, key)
