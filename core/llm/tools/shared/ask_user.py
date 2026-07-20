"""ask_user_question 工具执行：A2UI 弹窗收集用户补充信息。"""

from __future__ import annotations

import json
from typing import Any

from core.llm.a2ui.manager import (
    ConfirmationManager,
    ConfirmationRejectedError,
    ConfirmationTimeoutError,
)
from core.llm.a2ui.schemas import A2UIComponent


def format_ask_user_observation(observation: str, values: dict[str, Any]) -> str:
    """合并 LLM observation 与用户表单 values，供 ReAct OBSERVATION 与 UI 展示。"""
    obs = observation.strip()
    if not values:
        return obs or "用户未提供补充信息。"
    values_json = json.dumps(values, ensure_ascii=False)
    if not obs:
        return f"已收集用户补充信息：{values_json}"
    return f"{obs}\n用户回答：{values_json}"


def normalize_ask_user_action_input(action_input: dict[str, Any]) -> dict[str, Any]:
    """规范化 ask_user_question 的 action_input。"""
    return dict(action_input or {})


def merge_user_answers_into_brief(task_brief: str, values: dict[str, Any]) -> str:
    """将用户回答追加到任务简报。"""
    if not values:
        return task_brief
    lines = [task_brief.rstrip(), "用户补充："]
    for key, val in values.items():
        if key in ("intent", "feedback", "confirm_checkbox"):
            continue
        if val is None or val == "":
            continue
        lines.append(f"- {key}: {val}")
    return "\n".join(lines)


def _questions_to_components(questions: list[Any]) -> list[A2UIComponent]:
    components: list[A2UIComponent] = []
    for raw in questions:
        if not isinstance(raw, dict):
            continue
        qid = str(raw.get("id", "")).strip()
        if not qid:
            continue
        component = str(raw.get("component", "text")).strip() or "text"
        if component not in ("text", "select", "checkbox"):
            component = "text"
        options = raw.get("options") or []
        if not isinstance(options, list):
            options = []
        default = raw.get("default", "" if component != "checkbox" else False)
        if component == "select" and (default is None or str(default).strip() == ""):
            for opt in options:
                if not isinstance(opt, dict):
                    continue
                candidate = str(opt.get("value", "")).strip()
                if candidate:
                    default = opt.get("value", "")
                    break
            if default is None or str(default).strip() == "":
                first = options[0] if options and isinstance(options[0], dict) else {}
                default = first.get("value", "") if isinstance(first, dict) else ""
        components.append(
            A2UIComponent(
                id=qid,
                component=component,  # type: ignore[arg-type]
                label=str(raw.get("prompt", qid)),
                value=default,
                options=options,
                required=bool(raw.get("required", False)),
            )
        )
    return components


async def execute_ask_user_question(
    confirmation: ConfirmationManager,
    action_input: dict[str, Any],
    *,
    step_id: str = "",
    conversation_id: str = "",
) -> tuple[str, dict[str, Any]]:
    """发起 A2UI 提问并返回 observation 与用户 values。"""
    action_input = normalize_ask_user_action_input(dict(action_input or {}))
    title = str(action_input.get("title", "")).strip() or "请补充信息"
    description = str(action_input.get("description", "")).strip()
    questions = action_input.get("questions") or []
    if not isinstance(questions, list) or not questions:
        raise ValueError("ask_user_question 需要非空 questions 数组")

    components = _questions_to_components(questions)
    if not components:
        raise ValueError("ask_user_question questions 无效")

    try:
        response = await confirmation.request_user_questions(
            title=title,
            description=description,
            questions=list(questions),
            step_id=step_id or None,
            conversation_id=conversation_id or None,
        )
    except ConfirmationTimeoutError:
        return "用户确认超时，未收到回答。", {}
    except ConfirmationRejectedError as e:
        return f"用户取消了补充信息请求：{e}", {}

    if not response.approved:
        return "用户未确认补充信息。", {}

    values = dict(response.values or {})
    observation = format_ask_user_observation(
        str(action_input.get("observation", "")),
        values,
    )
    return observation, values
