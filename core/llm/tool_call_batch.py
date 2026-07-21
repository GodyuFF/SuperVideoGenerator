"""同轮多 tool_calls：独占校验、并行/顺序分流与 observation 合并。"""

from __future__ import annotations

import os
from typing import Literal

from core.llm.tools.shared.agent_tools import ASK_USER_QUESTION_ACTION

ReactChannel = Literal["master", "sub_agent"]
BatchExecutionMode = Literal["parallel", "sequential"]


class ExclusiveToolBatchError(ValueError):
    """独占 action（finish / ask_user_question / delegate_agent）与其他 tool 同轮混用。"""


# 同轮只能单独出现的 action
EXCLUSIVE_ACTIONS = frozenset(
    {
        "finish",
        ASK_USER_QUESTION_ACTION,
        "delegate_agent",
        "update_plan",
        "replan",
    }
)

# 子 Agent 默认可并行（无依赖的 create/read）
SUB_AGENT_PARALLEL_SAFE_PREFIXES = ("create_", "update_", "delete_")
SUB_AGENT_PARALLEL_SAFE_NAMES = frozenset(
    {
        "list_text_assets",
        "get_text_asset",
        "list_assets",
        "get_asset",
    }
)

# 主编排可并行的 tool_* 只读查询
MASTER_PARALLEL_TOOL_PREFIX = "tool_"


def max_parallel_tools() -> int:
    """单轮 ReAct 允许的最大并行/顺序 tool 数。"""
    raw = os.environ.get("SVG_REACT_MAX_PARALLEL_TOOLS", "16").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 16
    return max(1, min(value, 32))


def is_sub_agent_parallel_safe(action: str) -> bool:
    """子 Agent action 是否可在同轮与其他 action 并行。"""
    name = str(action or "").strip()
    if not name or name in EXCLUSIVE_ACTIONS:
        return False
    if name in SUB_AGENT_PARALLEL_SAFE_NAMES:
        return True
    return name.startswith(SUB_AGENT_PARALLEL_SAFE_PREFIXES)


def is_master_parallel_safe(action: str) -> bool:
    """主编排 action 是否可在同轮并行（仅 tool_*）。"""
    name = str(action or "").strip()
    if not name or name in EXCLUSIVE_ACTIONS:
        return False
    return name.startswith(MASTER_PARALLEL_TOOL_PREFIX)


def is_parallel_safe(action: str, *, channel: ReactChannel) -> bool:
    """按通道判断 action 是否适合同轮并行。"""
    if channel == "master":
        return is_master_parallel_safe(action)
    return is_sub_agent_parallel_safe(action)


def resolve_batch_execution_mode(
    actions: list[str],
    *,
    channel: ReactChannel,
) -> BatchExecutionMode:
    """解析同轮多 tool 的执行模式：全白名单则并行，否则顺序。"""
    if len(actions) <= 1:
        return "parallel"
    if all(is_parallel_safe(a, channel=channel) for a in actions):
        return "parallel"
    return "sequential"


def validate_tool_call_batch(
    actions: list[str],
    *,
    channel: ReactChannel,
) -> BatchExecutionMode:
    """校验同轮 tool_calls；独占混用则 raise，否则返回 parallel/sequential。"""
    if not actions:
        raise ValueError("tool_calls 不能为空")
    if len(actions) > max_parallel_tools():
        raise ValueError(
            f"单轮 tool_calls 数量 {len(actions)} 超过上限 {max_parallel_tools()}"
        )

    exclusive = [a for a in actions if a in EXCLUSIVE_ACTIONS]
    if exclusive and len(actions) > 1:
        exclusive_name = exclusive[0]
        others = [a for a in actions if a != exclusive_name]
        raise ExclusiveToolBatchError(
            f"action「{exclusive_name}」不可与其他 tool 同轮调用"
            f"（本轮同时返回了：{', '.join(actions)}）。"
            f"下一轮只能单独调用「{exclusive_name}」；"
            f"若需先查询，请先单独调用 {', '.join(others)}，完成后再单独委派/结束。"
        )

    return resolve_batch_execution_mode(actions, channel=channel)


def merge_batch_observations(
    items: list[tuple[str, str, str | BaseException]],
) -> str:
    """合并同轮多 tool 执行结果：(action, tool_call_id, observation_or_exc)。"""
    lines: list[str] = []
    for idx, (action, _tid, result) in enumerate(items, start=1):
        if isinstance(result, BaseException):
            lines.append(f"{idx}. {action}: 失败 — {result}")
        else:
            text = str(result).strip()
            if len(text) > 800:
                text = text[:799] + "…"
            lines.append(f"{idx}. {action}: {text}")
    return "\n".join(lines)
