"""OpenAI 风格 tool_calls ReAct 协议：解析 LLM 响应。"""

from core.llm.agent.react_core import ReActDecision, ToolCallDecision
from core.llm.json_parse import parse_tool_arguments
from core.llm.client.tool_calls import ToolCallResult
from core.llm.tool_call_batch import ReactChannel, validate_tool_call_batch


def _strip_nested_json_error(message: str) -> str:
    """去掉重复的「LLM 返回非合法 JSON:」前缀。"""
    prefix = "LLM 返回非合法 JSON: "
    while message.startswith(prefix):
        message = message[len(prefix) :]
    return message


def _parse_single_tool_call(tc: dict) -> ToolCallDecision:
    """解析单条 tool_call 为 ToolCallDecision。"""
    fn = tc.get("function") or {}
    action = str(fn.get("name", "")).strip()
    raw_args = fn.get("arguments", "{}")
    try:
        action_input = parse_tool_arguments(raw_args)
    except ValueError as e:
        inner = _strip_nested_json_error(str(e))
        raise ValueError(f"无法解析 tool arguments: {inner}") from e
    tool_call_id = str(tc.get("id", "")).strip()
    return ToolCallDecision(
        tool_call_id=tool_call_id,
        action=action,
        action_input=action_input,
    )


def parse_react_tool_calls_batch(
    result: ToolCallResult,
    *,
    channel: ReactChannel = "sub_agent",
) -> ReActDecision:
    """解析 LLM 全部 tool_calls 为 ReActDecision（支持同轮多 tool）。"""
    if not result.tool_calls:
        raise ValueError("LLM 响应缺少 tool_calls")
    calls = [_parse_single_tool_call(tc) for tc in result.tool_calls]
    actions = [c.action for c in calls]
    batch_mode = validate_tool_call_batch(actions, channel=channel)
    return ReActDecision(
        thought=(result.thinking or result.content).strip(),
        action=calls[0].action,
        action_input=dict(calls[0].action_input or {}),
        calls=calls,
        batch_mode=batch_mode,
    )


def parse_react_tool_calls(result: ToolCallResult) -> ReActDecision:
    """解析 LLM tool_calls 响应为 ReActDecision（兼容单 tool）。"""
    return parse_react_tool_calls_batch(result, channel="sub_agent")
