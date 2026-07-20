"""JSON Schema 校验（MCP tools/call 入参/出参）。"""

from __future__ import annotations

from typing import Any

import jsonschema
from jsonschema import ValidationError


def validate_against_schema(
    instance: Any,
    schema: dict[str, Any],
    *,
    label: str,
    tool_name: str | None = None,
) -> None:
    """按 JSON Schema 校验实例；失败时附带 tool 名与 required 字段便于定位。"""
    if not schema:
        return
    try:
        jsonschema.validate(instance=instance, schema=schema)
    except ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else "(root)"
        detail = f"{label} 不符合 schema：{path} {e.message}"
        if tool_name:
            detail += f" tool={tool_name}"
        required = schema.get("required")
        if required:
            detail += f" required={required}"
        raise ValueError(detail) from e
