"""主编排 delegate / finish 的 input schema。"""

from __future__ import annotations

from typing import Any

from core.llm.tools.shared.input_common import (
    FINISH_SCHEMA,
    REACT_INPUT_SCHEMA,
)


def build_master_delegate_schema() -> dict[str, Any]:
    """委派子 Agent 的 ReAct 入参 schema（计划回写改走 update_plan/replan）。"""
    return dict(REACT_INPUT_SCHEMA)


def build_master_finish_schema() -> dict[str, Any]:
    """主编排 finish 入参 schema。"""
    base = dict(FINISH_SCHEMA)
    base["additionalProperties"] = True
    return base
