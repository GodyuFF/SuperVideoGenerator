"""提示词组装：固定区（system）与动态区（user）分离。"""

import json
from typing import Any

from core.prompt.loader import load_required, load_text
from core.prompt.registry import (
    PromptProfile,
    get_action_json_system_base,
    get_agent_action_hint,
    get_agent_actions_prompt,
    get_react_system_prompt,
)
from core.prompt.sections import (
    BOUNDARY_MARKER,
    SystemPromptSection,
    assemble_system_prompt,
    make_section,
    register_section,
)


def render_template(template_name: str, slots: dict[str, str]) -> str:
    """轻量 {{slot}} 替换，不引入模板引擎依赖。"""
    text = load_required(f"templates/{template_name}")
    for key, value in slots.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def build_react_system(role_prompt: str = "") -> str:
    """ReAct 决策固定 system prompt（全局 JSON 协议 + Agent 角色）。"""
    base = get_react_system_prompt()
    if role_prompt.strip():
        return f"{base}\n\n## Agent Role\n{role_prompt.strip()}"
    return base


def build_action_system(agent_name: str, profile: PromptProfile = PromptProfile.DEFAULT) -> str:
    """行动执行固定 system prompt：全局 JSON 协议 + Agent actions + hint。"""
    parts = [get_action_json_system_base()]
    actions_doc = get_agent_actions_prompt(agent_name)
    if actions_doc:
        parts.append(f"\n## 本 Agent 行动字段\n{actions_doc}")
    hint = get_agent_action_hint(agent_name, profile)
    if hint.strip():
        parts.append(f"\n## 模式补充\n{hint.strip()}")
    return "\n".join(parts)


def build_react_json_user(
    *,
    task_brief: str,
    available_actions: list[str],
    completed: list[str],
    observations: list[str] | None = None,
    extra: dict[str, Any] | None = None,
    include_observations: bool = True,
) -> str:
    """子 Agent / 主编排 ReAct 动态 user 上下文（JSON）。"""
    ctx: dict[str, Any] = {
        "task_brief": task_brief,
        "available_actions": available_actions,
        "completed_actions": completed or ["无"],
    }
    if include_observations:
        ctx["observations"] = observations or ["无"]
    if extra:
        ctx.update(extra)
    return json.dumps(ctx, ensure_ascii=False, indent=2)


def build_action_user(slots: dict[str, str]) -> str:
    """子 Agent 行动执行动态 user 上下文（文本）。"""
    defaults = {
        "display_name": "",
        "role_prompt": "",
        "task_brief": "",
        "work_context_line": "",
        "store_context": "",
        "current_action": "",
        "completed_actions": "",
        "history_summary_block": "",
        "observations_block": "",
    }
    merged = {**defaults, **slots}
    return render_template("action_context.txt", merged)


def get_summary_system_prompt() -> str:
    return load_text("agents/super_video_master/fixed/summary.md") or (
        "你是视频制作助手。根据执行结果为用户写一段简短中文回复（2-4 句）。"
        "直接输出正文，不要使用 JSON、Markdown 或代码块。"
    )
