"""聚合各域 action input schema（供 Registry 与 prompt 层引用）。"""

from __future__ import annotations

from typing import Any

from core.llm.prompt.tools.schema_builders import build_ask_user_question_schema
from core.llm.tools.editing.schemas import EDITING_SCHEMAS
from core.llm.tools.image.schemas import IMAGE_SCHEMAS
from core.llm.tools.plan.schemas import REPLAN_SCHEMA, UPDATE_PLAN_SCHEMA
from core.llm.tools.script.schemas import SCRIPT_SCHEMAS
from core.llm.tools.shared.input_common import (
    FINISH_SCHEMA,
    OBSERVATION_ONLY,
    REACT_INPUT_SCHEMA,
)
from core.llm.tools.storyboard.schemas import STORYBOARD_SCHEMAS
from core.llm.tools.storyboard_refine.schemas import STORYBOARD_REFINE_SCHEMAS
from core.llm.tools.tts.schemas import TTS_SCHEMAS
from core.llm.tools.video.schemas import VIDEO_SCHEMAS
from core.llm.tools.shared.return_to_master_schema import RETURN_TO_MASTER_SCHEMA
from core.llm.tools.web_fetch.schemas import (
    read_webpage_input_schema,
    read_webpage_react_input_schema,
)

ASK_USER_QUESTION_ACTION = "ask_user_question"
_ASK_USER_QUESTION_SCHEMA = build_ask_user_question_schema()

_READ_ONLY_REACT_ACTIONS = frozenset(
    {
        "list_text_assets",
        "list_images",
        "get_plan",
        "get_refine_plan",
        "list_videos",
        "list_audio",
        "list_final",
    }
)

_WEB_FETCH_SCHEMAS: dict[str, dict[str, Any]] = {
    "read_webpage": read_webpage_input_schema(),
}

ACTION_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "finish": FINISH_SCHEMA,
    "return_to_master": RETURN_TO_MASTER_SCHEMA,
    ASK_USER_QUESTION_ACTION: _ASK_USER_QUESTION_SCHEMA,
    "update_plan": UPDATE_PLAN_SCHEMA,
    "replan": REPLAN_SCHEMA,
    **SCRIPT_SCHEMAS,
    **IMAGE_SCHEMAS,
    **STORYBOARD_SCHEMAS,
    **STORYBOARD_REFINE_SCHEMAS,
    **VIDEO_SCHEMAS,
    **TTS_SCHEMAS,
    **EDITING_SCHEMAS,
    **_WEB_FETCH_SCHEMAS,
}


def react_input_schema(action: str) -> dict[str, Any]:
    """ReAct 决策阶段 schema（计划字段仅 update_plan/replan 必填）。"""
    if action == "finish":
        base = dict(FINISH_SCHEMA)
        base["additionalProperties"] = True
        return base
    if action == ASK_USER_QUESTION_ACTION:
        return dict(_ASK_USER_QUESTION_SCHEMA)
    if action == "update_plan":
        return dict(UPDATE_PLAN_SCHEMA)
    if action == "replan":
        return dict(REPLAN_SCHEMA)
    if action == "read_webpage":
        return read_webpage_react_input_schema()
    if action in _READ_ONLY_REACT_ACTIONS:
        return dict(REACT_INPUT_SCHEMA)
    return dict(REACT_INPUT_SCHEMA)


def action_input_schema(action: str) -> dict[str, Any]:
    """行动执行阶段完整 schema。"""
    schema = ACTION_INPUT_SCHEMAS.get(action)
    if schema:
        return dict(schema)
    try:
        from core.llm.tools.registry import get_tool_registry

        spec = get_tool_registry().get(action)
        if spec is not None:
            return dict(spec.input_schema)
    except Exception:
        pass
    return dict(OBSERVATION_ONLY)
