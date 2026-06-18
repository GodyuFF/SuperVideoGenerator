"""敏感字段脱敏，写入持久化日志前使用。"""

import copy
import re
from typing import Any

_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "password",
        "secret",
        "token",
    }
)

_API_KEY_PATTERN = re.compile(r"sk-[a-zA-Z0-9_-]{8,}")


def _mask_value(key: str, value: Any) -> Any:
    if isinstance(value, str):
        if key.lower() in _SENSITIVE_KEYS or "api_key" in key.lower():
            return "***" if value else value
        if _API_KEY_PATTERN.search(value):
            return _API_KEY_PATTERN.sub("sk-***", value)
    return value


def redact_for_log(data: Any) -> Any:
    """深拷贝并脱敏，适合 JSON 序列化入库。"""
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for k, v in data.items():
            if k.lower() in _SENSITIVE_KEYS:
                out[k] = "***"
            elif isinstance(v, (dict, list)):
                out[k] = redact_for_log(v)
            else:
                out[k] = _mask_value(k, v)
        return out
    if isinstance(data, list):
        return [redact_for_log(x) for x in data]
    if isinstance(data, str) and _API_KEY_PATTERN.search(data):
        return _API_KEY_PATTERN.sub("sk-***", data)
    return data


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    out = copy.copy(headers)
    for k in list(out.keys()):
        if k.lower() == "authorization":
            out[k] = "Bearer ***"
    return out
