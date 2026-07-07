"""tts_agent 相关 action input schema."""

from __future__ import annotations

from typing import Any

from core.llm.prompt.tools.schema_builders import _OBSERVATION
from core.llm.tools.shared.input_common import OBSERVATION_ONLY, READ_ONLY_QUERY_SCHEMA

TTS_SYNTH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "observation": _OBSERVATION,
        "shot_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "可选：仅合成指定镜头；省略则合成全部旁白",
        },
    },
    "required": ["observation"],
    "additionalProperties": True,
}

TTS_SCHEMAS: dict[str, dict[str, Any]] = {
    "extract_narration": dict(OBSERVATION_ONLY),
    "synthesize": TTS_SYNTH_SCHEMA,
    "list_audio": READ_ONLY_QUERY_SCHEMA,
}
