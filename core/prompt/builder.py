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


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_template(template_name: str, slots: dict[str, str]) -> str:
    """轻量 {{slot}} 替换，不引入模板引擎依赖。"""
    text = load_required(f"templates/{template_name}")
    for key, value in slots.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def _actions_xml(actions: list[str]) -> str:
    if not actions:
        return "    <action>无</action>"
    return "\n".join(f"    <action>{_escape_xml(a)}</action>" for a in actions)


def _items_xml(items: list[str], *, empty_label: str = "无") -> str:
    if not items:
        return f"    <item>{empty_label}</item>"
    return "\n".join(f"    <item>{_escape_xml(i)}</item>" for i in items)


def _extra_xml(extra: dict[str, Any] | None) -> str:
    if not extra:
        return ""
    parts = [f"    <{k}>{_escape_xml(str(v))}</{k}>" for k, v in extra.items() if v]
    if not parts:
        return ""
    return "\n  <extra>\n" + "\n".join(parts) + "\n  </extra>"


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


def build_react_user(
    *,
    task_brief: str,
    available_actions: list[str],
    completed: list[str],
    observations: list[str],
    extra: dict[str, Any] | None = None,
) -> str:
    """子 Agent ReAct 动态 user 上下文（XML）。角色已移至 system 静态区。"""
    return render_template(
        "react_context.xml",
        {
            "task_brief": _escape_xml(task_brief),
            "available_actions_xml": _actions_xml(available_actions),
            "completed_actions_xml": _items_xml(completed),
            "observations_xml": _items_xml(observations),
            "extra_xml": _extra_xml(extra),
        },
    )


def build_react_json_user(
    *,
    task_brief: str,
    available_actions: list[str],
    completed: list[str],
    observations: list[str],
    extra: dict[str, Any] | None = None,
) -> str:
    """子 Agent ReAct 动态 user 上下文（JSON，OpenAI 协议）。"""
    ctx = {
        "task_brief": task_brief,
        "available_actions": available_actions,
        "completed_actions": completed or ["无"],
        "observations": observations or ["无"],
    }
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


def build_react_session_user(session: Any) -> str:
    """主编排 ReAct 动态 user 上下文（XML）。"""
    agents_xml = "\n".join(
        f"    <sub_agent>"
        f"<delegate_action>{_escape_xml(sa.delegate_action)}</delegate_action>"
        f"<agent_name>{_escape_xml(sa.agent_name)}</agent_name>"
        f"<display_name>{_escape_xml(sa.display_name)}</display_name>"
        f"<description>{_escape_xml(sa.description)}</description>"
        f"</sub_agent>"
        for sa in session.sub_agents
    )
    tools_xml = "\n".join(
        f"    <tool>"
        f"<action>{_escape_xml(t.action_name)}</action>"
        f"<name>{_escape_xml(t.name)}</name>"
        f"<description>{_escape_xml(t.description)}</description>"
        f"</tool>"
        for t in session.tools
    ) or "    <tool>无</tool>"
    extra = dict(session.extra or {})
    extra_xml = _extra_xml(extra)
    user_summary_xml = ""
    if session.user_summary:
        user_summary_xml = (
            f"\n  <user_summary>{_escape_xml(session.user_summary)}</user_summary>"
        )
    return render_template(
        "react_session.xml",
        {
            "conversation_id": _escape_xml(session.conversation_id),
            "agent_name": _escape_xml(session.agent_name),
            "agent_name_inner": _escape_xml(session.agent.name),
            "agent_display_name": _escape_xml(session.agent.display_name),
            "agent_description": _escape_xml(session.agent.description),
            "task_brief": _escape_xml(session.task_brief),
            "sub_agents_xml": agents_xml,
            "tools_xml": tools_xml,
            "available_actions_xml": _actions_xml(session.available_actions()),
            "completed_xml": _items_xml(session.completed_labels()),
            "observations_xml": _items_xml(list(session.observations)),
            "extra_xml": extra_xml + user_summary_xml,
        },
    )


def get_summary_system_prompt() -> str:
    return load_text("agents/super_video_master/fixed/summary.md") or (
        "你是视频制作助手。根据执行结果为用户写一段简短中文回复（2-4 句）。"
        "直接输出正文，不要使用 JSON、Markdown 或代码块。"
    )
