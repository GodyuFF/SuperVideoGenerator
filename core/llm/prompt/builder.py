"""提示词组装：固定区（system）与动态区（user）分离。"""

import json
from typing import Any

from core.llm.prompt.loader import load_required, load_text
from core.llm.prompt.registry import (
    PromptProfile,
    get_action_json_system_base,
    get_agent_action_hint,
    get_react_system_prompt,
)
from core.llm.prompt.chat_messages import (
    ACTION_CONTEXT_HEADER,
    MASTER_STATE_INSTRUCTIONS,
    REACT_STATE_HEADER,
)
from core.llm.tools.shared.agent_tools import should_hide_when_completed


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


def build_action_system(agent_name: str, profile: PromptProfile | str = PromptProfile.DEFAULT) -> str:
    """行动执行固定 system prompt：全局 tool 协议 + profile hint。"""
    parts = [get_action_json_system_base()]
    hint = get_agent_action_hint(agent_name, profile)
    if hint.strip():
        parts.append(f"\n## 模式补充\n{hint.strip()}")
    return "\n".join(parts)


_PLACEHOLDER_COMPLETED = frozenset({"无", ""})


def normalize_completed_names(completed: list[str]) -> set[str]:
    """将 completed_actions 规范化为可与 available_actions 比对的名称集合。"""
    names: set[str] = set()
    for raw in completed:
        item = str(raw).strip()
        if not item or item in _PLACEHOLDER_COMPLETED:
            continue
        names.add(item)
        if item.startswith("tool:"):
            names.add(f"tool_{item.removeprefix('tool:')}")
    return names


def filter_available_actions(
    available_actions: list[str],
    completed: list[str],
) -> list[str]:
    """从 available_actions 中剔除已完成的一次性步骤（保持原顺序）。"""
    done = normalize_completed_names(completed)
    if not done:
        return list(available_actions)
    return [
        action
        for action in available_actions
        if action not in done or not should_hide_when_completed(action)
    ]


def build_react_static_system(
    role_prompt: str = "",
    *,
    goal_mode: bool = False,
    agent_name: str = "",
    profile: PromptProfile | str = "",
) -> str:
    """ReAct 静态 system：全局协议 + 角色 + 可选模式 hint + goal_mode 规则。"""
    base = build_react_system(role_prompt)
    if agent_name and profile:
        hint = get_agent_action_hint(agent_name, profile)
        if hint.strip():
            base = f"{base}\n\n## 模式补充\n{hint.strip()}"
    if goal_mode:
        extra = load_text("rules/goal_mode.md")
        if extra:
            base = f"{base}\n\n{extra}"
    return base


def build_react_state_turn_content(
    state_json: str,
    *,
    hint: str = "",
    instructions: str | None = None,
) -> str:
    """ReAct 动态编排状态（拼入 messages 末条 user）。"""
    instr = instructions or MASTER_STATE_INSTRUCTIONS
    parts = [REACT_STATE_HEADER, state_json]
    if hint.strip():
        parts.extend(["", hint.strip()])
    parts.extend(["", instr])
    return "\n".join(parts)


def build_action_context_turn_content(action_context: str) -> str:
    """行动执行动态上下文（拼入 messages 末条 user）。"""
    ctx = action_context.strip()
    if not ctx:
        return ""
    return f"{ACTION_CONTEXT_HEADER}\n{ctx}"


def build_react_state_json(
    *,
    task_brief: str,
    available_actions: list[str],
    completed: list[str],
    observations: list[str] | None = None,
    extra: dict[str, Any] | None = None,
    include_observations: bool = True,
) -> str:
    """ReAct 动态编排状态 JSON（由 build_react_state_turn_content 拼入末条 user）。"""
    prompt_actions = filter_available_actions(available_actions, completed)
    ctx: dict[str, Any] = {
        "task_brief": task_brief,
        "available_actions": prompt_actions,
        "completed_actions": completed or ["无"],
    }
    if include_observations:
        ctx["observations"] = observations or ["无"]
    if extra:
        ctx.update(extra)
    return json.dumps(ctx, ensure_ascii=False, indent=2)


def build_action_user(slots: dict[str, str]) -> str:
    """子 Agent 行动执行动态上下文文本（由 build_action_context_turn_content 拼入末条 user）。"""
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
