"""JSON Schema 校验（MCP tools/call 入参/出参）。"""

from __future__ import annotations

from typing import Any

import jsonschema
from jsonschema import ValidationError


def validate_against_schema(instance: Any, schema: dict[str, Any], *, label: str) -> None:
    if not schema:
        return
    try:
        jsonschema.validate(instance=instance, schema=schema)
    except ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else "(root)"
        raise ValueError(f"{label} 不符合 schema：{path} {e.message}") from e
