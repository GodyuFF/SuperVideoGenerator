"""OpenAI 风格 JSON ReAct 协议：解析 LLM 响应。"""

import json
import re
from typing import Any

from core.agents.react_core import ReActDecision


def parse_react_json(text: str | dict[str, Any]) -> ReActDecision:
    """解析 LLM 返回的 JSON ReAct 响应（支持已解析的 dict）。"""
    if isinstance(text, dict):
        data = text
        return ReActDecision(
            thought=str(data.get("thought", "")).strip(),
            action=str(data.get("action", "")).strip(),
            action_input=data.get("action_input") or {},
        )

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

    thought_m = re.search(r'"thought"\s*:\s*"([^"]*)"', text)
    action_m = re.search(r'"action"\s*:\s*"([^"]*)"', text)
    if action_m:
        return ReActDecision(
            thought=thought_m.group(1).strip() if thought_m else "",
            action=action_m.group(1).strip(),
        )

    raise ValueError("无法解析 LLM 的 JSON ReAct 响应")
