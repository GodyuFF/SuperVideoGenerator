"""OpenAI 风格 tool_calls ReAct 协议：解析 LLM 响应。"""

import json
import re
from typing import Any

from core.llm.agent.react_core import ReActDecision
from core.llm.json_parse import parse_tool_arguments
from core.llm.client.tool_calls import ToolCallResult


def _strip_nested_json_error(message: str) -> str:
    """去掉重复的「LLM 返回非合法 JSON:」前缀。"""
    prefix = "LLM 返回非合法 JSON: "
    while message.startswith(prefix):
        message = message[len(prefix) :]
    return message


def parse_react_tool_calls(result: ToolCallResult) -> ReActDecision:
    """解析 LLM tool_calls 响应为 ReActDecision。"""
    if not result.tool_calls:
        raise ValueError("LLM 响应缺少 tool_calls")
    tc = result.tool_calls[0]
    fn = tc.get("function") or {}
    action = str(fn.get("name", "")).strip()
    raw_args = fn.get("arguments", "{}")
    try:
        action_input = parse_tool_arguments(raw_args)
    except ValueError as e:
        inner = _strip_nested_json_error(str(e))
        raise ValueError(f"无法解析 tool arguments: {inner}") from e
    return ReActDecision(
        thought=(result.thinking or result.content).strip(),
        action=action,
        action_input=action_input,
    )


def parse_react_json(text: str | dict[str, Any]) -> ReActDecision:
    """解析 LLM 返回的 JSON ReAct 响应（legacy，测试兼容）。"""
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
