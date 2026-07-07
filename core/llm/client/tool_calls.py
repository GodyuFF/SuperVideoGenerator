"""OpenAI tool_calls 响应模型。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCallResult:
    """单次 Chat Completions tool_calls 响应。"""

    content: str = ""
    thinking: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw_message: dict[str, Any] = field(default_factory=dict)

    def primary_tool_call(self) -> dict[str, Any] | None:
        return self.tool_calls[0] if self.tool_calls else None

    def primary_arguments(self) -> dict[str, Any]:
        tc = self.primary_tool_call()
        if not tc:
            return {}
        fn = tc.get("function") or {}
        raw = fn.get("arguments", "{}")
        if isinstance(raw, dict):
            return raw
        try:
            parsed = json.loads(str(raw))
            return parsed if isinstance(parsed, dict) else {"raw": parsed}
        except json.JSONDecodeError:
            return {"raw": raw}

    def primary_name(self) -> str:
        tc = self.primary_tool_call()
        if not tc:
            return ""
        return str((tc.get("function") or {}).get("name", "")).strip()
