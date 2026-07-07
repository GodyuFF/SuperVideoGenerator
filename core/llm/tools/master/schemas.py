"""主编排 delegate / finish 的 input schema。"""

from __future__ import annotations

from typing import Any

from core.llm.tools.shared.input_common import (
    FINISH_SCHEMA,
    REACT_INPUT_SCHEMA,
    merge_plan_tracking,
)


def build_master_delegate_schema() -> dict[str, Any]:
    return merge_plan_tracking(dict(REACT_INPUT_SCHEMA))


def build_master_finish_schema() -> dict[str, Any]:
    base = dict(FINISH_SCHEMA)
    base["additionalProperties"] = True
    return merge_plan_tracking(base)
