"""项目/剧本上下文：供子 Agent ReAct 与行动执行注入。"""

from __future__ import annotations

from typing import Any

from core.guards.script_style import format_style_hints_line, normalize_style_mode_id
from core.store.memory import MemoryStore


def build_project_script_context(
    store: MemoryStore,
    work_context: dict[str, Any],
) -> dict[str, Any]:
    """从 work_context + MemoryStore 组装项目/剧本基本信息。"""
    project_id = str(work_context.get("project_id", "")).strip()
    script_id = str(work_context.get("script_id", "")).strip()
    ctx: dict[str, Any] = {
        "project_id": project_id,
        "script_id": script_id,
        "conversation_id": str(work_context.get("conversation_id", "")).strip(),
    }

    style_mode = work_context.get("style_mode")
    if style_mode is not None:
        ctx["style_mode"] = str(
            style_mode.value if hasattr(style_mode, "value") else style_mode
        )

    generation_mode = work_context.get("generation_mode")
    if generation_mode is not None:
        ctx["generation_mode"] = str(
            generation_mode.value if hasattr(generation_mode, "value") else generation_mode
        )

    if project_id:
        project = store.get_project(project_id)
        if project:
            ctx["project_title"] = project.title

    if script_id:
        script = store.get_script(script_id)
        if script:
            ctx["script_title"] = script.title
            ctx["script_status"] = script.status.value
            ctx["duration_sec"] = script.duration_sec
            if script.style_mode and "style_mode" not in ctx:
                ctx["style_mode"] = normalize_style_mode_id(script.style_mode)
            hints_line = format_style_hints_line(script.style_hints)
            if hints_line:
                ctx["style_hints"] = hints_line

    return ctx


def format_project_context_line(context: dict[str, Any]) -> str:
    """单行工作上下文（行动执行模板用）。"""
    parts: list[str] = []
    if context.get("project_id"):
        title = context.get("project_title") or "未命名项目"
        parts.append(f"项目={title}({context['project_id']})")
    if context.get("script_id"):
        title = context.get("script_title") or "未命名剧本"
        status = context.get("script_status", "")
        status_part = f", status={status}" if status else ""
        parts.append(f"剧本={title}({context['script_id']}{status_part})")
    for key in ("style_mode", "style_hints", "generation_mode", "conversation_id", "duration_sec"):
        if key in context and context[key]:
            parts.append(f"{key}={context[key]}")
    return ", ".join(parts)


def format_project_context_header(context: dict[str, Any]) -> str:
    """ReAct anchor_user 前缀摘要。"""
    line = format_project_context_line(context)
    return f"【项目上下文】{line}" if line else ""
