"""OpenAI 风格 JSON ReAct 协议：构建上下文与解析响应。"""

import json
import re
from typing import Any

from core.agents.react_core import ReActDecision


def build_react_json_context(
    role_description: str,
    task_brief: str,
    available_actions: list[str],
    completed: list[str],
    observations: list[str],
    extra: dict[str, Any] | None = None,
) -> str:
    """构建发给 LLM 的 JSON 格式 ReAct 上下文。"""
    ctx = {
        "role": role_description,
        "task_brief": task_brief,
        "available_actions": available_actions,
        "completed_actions": completed or ["无"],
        "observations": observations or ["无"],
    }
    if extra:
        ctx.update(extra)
    return json.dumps(ctx, ensure_ascii=False, indent=2)


def parse_react_json(text: str | dict[str, Any]) -> ReActDecision:
    """解析 LLM 返回的 JSON ReAct 响应（支持已解析的 dict）。"""
    if isinstance(text, dict):
        data = text
        return ReActDecision(
            thought=str(data.get("thought", "")).strip(),
            action=str(data.get("action", "")).strip(),
            action_input=data.get("action_input") or {},
        )

    # 尝试直接解析
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict):
            return ReActDecision(
                thought=str(data.get("thought", "")).strip(),
                action=str(data.get("action", "")).strip(),
                action_input=data.get("action_input") or {},
            )
    except json.JSONDecodeError:
        pass

    # 宽松提取：找第一个 { ... }
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            data = json.loads(match.group(0))
            return ReActDecision(
                thought=str(data.get("thought", "")).strip(),
                action=str(data.get("action", "")).strip(),
                action_input=data.get("action_input") or {},
            )
        except Exception:
            pass

    # 最后兜底：正则提取字段
    thought_m = re.search(r'"thought"\s*:\s*"([^"]*)"', text)
    action_m = re.search(r'"action"\s*:\s*"([^"]*)"', text)
    if action_m:
        return ReActDecision(
            thought=thought_m.group(1).strip() if thought_m else "",
            action=action_m.group(1).strip(),
        )

    raise ValueError("无法解析 LLM 的 JSON ReAct 响应")
