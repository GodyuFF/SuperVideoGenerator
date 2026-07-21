"""Canonical tool 定义构建：ReAct 决策与行动执行。"""

from __future__ import annotations

from typing import Any

from core.llm.tools.shared.agent_tools import ASK_USER_QUESTION_ACTION
from core.llm.model.llm_request import ToolDefinition
from core.llm.prompt.tools.schemas import action_input_schema, react_input_schema
from core.llm.tools.master.schemas import build_master_finish_schema
from core.llm.master.delegate_tool import (
    DELEGATE_AGENT_ACTION,
    build_delegate_agent_description,
    build_delegate_agent_input_schema,
)


def tool_choice_force(name: str) -> dict[str, str]:
    return {"type": "tool", "name": name}


def unique_actions(actions: list[str]) -> list[str]:
    """保序去重，避免 API tools[].name 重复。"""
    seen: set[str] = set()
    out: list[str] = []
    for action in actions:
        if action not in seen:
            seen.add(action)
            out.append(action)
    return out


def _master_action_description(action: str) -> str:
    if action == "finish":
        return "结束主编排 ReAct 循环，进入收尾摘要。"
    if action == ASK_USER_QUESTION_ACTION:
        return "向用户询问缺失信息（A2UI 弹窗），用于补充任务所需字段；计划确认时用 kind=plan_approval。"
    if action == DELEGATE_AGENT_ACTION:
        return "委派子 Agent 执行专项任务（需传入 agent_id）。"
    if action == "update_plan":
        return "回写计划进度 plan_status 与 remaining_plan（不提升 version）。"
    if action == "replan":
        return "结构化重规划：version++、修改步骤状态/跳过/重置，可选追加步骤。"
    if action.startswith("tool_"):
        return f"调用主编排工具 {action}"
    return action


def _sub_action_description(agent_name: str, action: str) -> str:
    if action == "finish":
        return "结束本子 Agent ReAct 循环。"
    from core.llm.tools.shared.agent_tools import get_agent_tools

    for spec in get_agent_tools().get(agent_name, []):
        if spec.action == action:
            return spec.description
    return f"执行行动 {action}"


def build_react_tool(action: str, description: str, *, input_schema: dict | None = None) -> ToolDefinition:
    return ToolDefinition(
        name=action,
        description=description,
        input_schema=input_schema or react_input_schema(action),
        kind="function",
    )


def build_delegate_agent_tool(
    profile_id: str,
    style_mode: Any,
    *,
    config: Any | None = None,
    delegate_readiness: list[dict[str, Any]] | None = None,
    eligible_agent_ids: list[str] | None = None,
) -> ToolDefinition:
    """构建会话感知的 delegate_agent 工具定义。"""
    return ToolDefinition(
        name=DELEGATE_AGENT_ACTION,
        description=build_delegate_agent_description(
            profile_id,
            style_mode,
            config=config,
            delegate_readiness=delegate_readiness,
            eligible_agent_ids=eligible_agent_ids,
        ),
        input_schema=build_delegate_agent_input_schema(
            profile_id,
            style_mode,
            config=config,
            eligible_agent_ids=eligible_agent_ids,
        ),
        kind="agent",
        agent_name="",
    )


def build_master_react_tool(
    action: str,
    *,
    profile_id: str | None = None,
    style_mode: Any | None = None,
    config: Any | None = None,
    delegate_readiness: list[dict[str, Any]] | None = None,
    eligible_delegate_agent_ids: list[str] | None = None,
) -> ToolDefinition:
    description = _master_action_description(action)
    if action == DELEGATE_AGENT_ACTION:
        pid = profile_id or "default"
        sm = style_mode or "storybook"
        return build_delegate_agent_tool(
            pid,
            sm,
            config=config,
            delegate_readiness=delegate_readiness,
            eligible_agent_ids=eligible_delegate_agent_ids,
        )
    if action == "finish":
        return ToolDefinition(
            name=action,
            description=description,
            input_schema=build_master_finish_schema(),
            kind="function",
        )
    if action == ASK_USER_QUESTION_ACTION:
        return ToolDefinition(
            name=action,
            description=description,
            input_schema=react_input_schema(ASK_USER_QUESTION_ACTION),
            kind="function",
        )
    if action in ("update_plan", "replan"):
        return ToolDefinition(
            name=action,
            description=description,
            input_schema=react_input_schema(action),
            kind="function",
        )
    if action == "tool_read_webpage":
        from core.llm.tools.web_fetch.schemas import read_webpage_react_input_schema

        return ToolDefinition(
            name=action,
            description="读取指定 URL 的网页正文（只读，http/https）",
            input_schema=read_webpage_react_input_schema(for_master=True),
            kind="function",
        )
    return build_react_tool(action, description)


def build_ask_user_question_tool() -> ToolDefinition:
    return ToolDefinition(
        name=ASK_USER_QUESTION_ACTION,
        description="向用户询问缺失信息（A2UI 弹窗）",
        input_schema=react_input_schema(ASK_USER_QUESTION_ACTION),
        kind="function",
    )


def _ensure_ask_tool(
    tools: list[ToolDefinition],
    *,
    include_ask_user: bool = True,
) -> list[ToolDefinition]:
    if not include_ask_user:
        return tools
    if any(t.name == ASK_USER_QUESTION_ACTION for t in tools):
        return tools
    return [*tools, build_ask_user_question_tool()]


def build_master_react_tools(
    available_actions: list[str],
    *,
    profile_id: str | None = None,
    style_mode: Any | None = None,
    config: Any | None = None,
    include_ask_user: bool | None = None,
    delegate_readiness: list[dict[str, Any]] | None = None,
    eligible_delegate_agent_ids: list[str] | None = None,
) -> list[ToolDefinition]:
    if include_ask_user is None:
        include_ask_user = True
    actions = unique_actions(available_actions)
    return _ensure_ask_tool(
        [
            build_master_react_tool(
                action,
                profile_id=profile_id,
                style_mode=style_mode,
                config=config,
                delegate_readiness=delegate_readiness,
                eligible_delegate_agent_ids=eligible_delegate_agent_ids,
            )
            for action in actions
        ],
        include_ask_user=include_ask_user,
    )


def build_sub_agent_react_tools(
    agent_name: str,
    available_actions: list[str],
    *,
    include_ask_user: bool | None = None,
) -> list[ToolDefinition]:
    from core.llm.tools import get_tool_registry

    registry = get_tool_registry()
    tools: list[ToolDefinition] = []
    for action in unique_actions(available_actions):
        if action == "finish":
            tools.append(
                build_react_tool(action, "结束本子 Agent ReAct 循环。", input_schema=react_input_schema("finish"))
            )
            continue
        spec = registry.get(action)
        if spec and (spec.agent == agent_name or spec.agent == "common"):
            tools.append(
                ToolDefinition(
                    name=action,
                    description=spec.description,
                    input_schema=dict(spec.input_schema),
                    output_schema=dict(spec.output_schema),
                    kind="function",
                )
            )
        else:
            tools.append(
                build_react_tool(action, _sub_action_description(agent_name, action))
            )
    if include_ask_user is None:
        include_ask_user = True
    return _ensure_ask_tool(tools, include_ask_user=include_ask_user)


def build_action_tool(agent_name: str, action: str) -> ToolDefinition:
    from core.llm.tools import get_tool_registry

    registry = get_tool_registry()
    spec = registry.get(action)
    if spec and (spec.agent == agent_name or spec.agent == "common"):
        return ToolDefinition(
            name=action,
            description=spec.description,
            input_schema=dict(spec.input_schema),
            output_schema=dict(spec.output_schema),
            kind="function",
        )
    return ToolDefinition(
        name=action,
        description=_sub_action_description(agent_name, action),
        input_schema=action_input_schema(action),
        kind="function",
    )


def tool_spec_for_action(agent_name: str, action: str):
    from core.llm.tools.shared.agent_tools import get_agent_tools

    for spec in get_agent_tools().get(agent_name, []):
        if spec.action == action:
            return spec
    return None
