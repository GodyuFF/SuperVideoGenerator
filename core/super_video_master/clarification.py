"""剧本需求补全（A2UI script_requirements）是否弹出的判定。"""

from __future__ import annotations

from typing import Any

from core.guards.script_style import normalize_style_hints, parse_target_duration_sec


def has_script_duration_context(
    *,
    user_text: str,
    script_duration_sec: int | None,
    script_style_hints: dict[str, Any] | None,
    requested_hints: dict[str, Any] | None,
) -> bool:
    """判断用户消息或剧本侧是否已具备可用的目标时长上下文。"""
    hinted = normalize_style_hints(requested_hints).get("target_duration")
    script_hinted = normalize_style_hints(script_style_hints).get("target_duration")
    text = (user_text or "").lower()
    return bool(
        hinted
        or script_hinted
        or (isinstance(script_duration_sec, int) and script_duration_sec > 0)
        or parse_target_duration_sec(user_text) is not None
        or any(kw in text for kw in ("秒", "时长", "分钟"))
    )


def should_request_script_requirements(
    *,
    goal: bool,
    style_known: bool,
    has_duration_context: bool,
    has_existing_script_body: bool,
) -> bool:
    """
    是否需要弹出剧本需求补全表单。

    - 目标模式：跳过
    - 剧本已有正文（如「重新设计」）：跳过，直接交给 AI
    - 风格与时长均已知：跳过
    """
    if goal or has_existing_script_body:
        return False
    return not (style_known and has_duration_context)
