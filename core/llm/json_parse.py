"""LLM 响应 JSON 容错解析（标准 JSON + Python dict 字面量）。"""

import ast
import json
import re
from typing import Any


def repair_json_string_literals(text: str) -> str:
    """
    修复 JSON 字符串值内未转义的双引号（LLM 流式 tool input 常见错误）。

    当处于字符串内部且遇到 `"` 时，若其后（跳过空白）不是 JSON 结构分隔符，
    则视为字符串内容，转义为 `\\"`。
    """
    if not text:
        return text
    out: list[str] = []
    in_string = False
    escape = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if escape:
            out.append(ch)
            escape = False
            i += 1
            continue
        if ch == "\\":
            out.append(ch)
            escape = True
            i += 1
            continue
        if ch != '"':
            out.append(ch)
            i += 1
            continue
        if not in_string:
            in_string = True
            out.append(ch)
            i += 1
            continue
        j = i + 1
        while j < n and text[j] in " \t\n\r":
            j += 1
        if j >= n or text[j] in ":,}]":
            in_string = False
            out.append(ch)
        else:
            out.append('\\"')
        i += 1
    return "".join(out)


def _coerce_nested_json_strings(data: dict[str, Any]) -> dict[str, Any]:
    """将顶层 content 等字段中嵌套的 JSON 字符串解析为对象。"""
    out = dict(data)
    content = out.get("content")
    if isinstance(content, str):
        stripped = content.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                nested = parse_tool_arguments(stripped)
            except ValueError:
                nested = None
            if isinstance(nested, dict):
                out["content"] = nested
    return out


def parse_llm_json_object(content: str) -> dict[str, Any]:
    """
    将 LLM 文本解析为 JSON 对象。

    依次尝试：标准 json.loads → ast.literal_eval（单引号 dict）→ 提取首个 {...} 块。
    """
    text = content.strip()
    if not text:
        raise ValueError("LLM 返回空内容")

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()

    candidates: list[str] = [text]
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace and brace.group(0) != text:
        candidates.append(brace.group(0))

    last_error: Exception | None = None
    for candidate in candidates:
        for loader in (json.loads, ast.literal_eval):
            try:
                data = loader(candidate)
            except (json.JSONDecodeError, SyntaxError, ValueError) as e:
                last_error = e
                continue
            if isinstance(data, dict):
                return data
            last_error = ValueError("响应必须是 JSON 对象")

    detail = str(last_error) if last_error else "无法解析"
    raise ValueError(f"LLM 返回非合法 JSON: {detail}: {content[:200]}")


def salvage_truncated_tool_arguments(text: str) -> dict[str, Any] | None:
    """
    截断的 tool arguments：保留 observation 等标量字段，丢弃未闭合的 items 等大数组。
    常见于 generate_images 填入冗长 image_prompt 导致 JSON 被 max_tokens 截断。
    """
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None

    obs_m = re.search(r'"observation"\s*:\s*"((?:\\.|[^"\\])*)"', stripped)
    if obs_m:
        try:
            observation = json.loads(f'"{obs_m.group(1)}"')
        except json.JSONDecodeError:
            observation = obs_m.group(1)
    else:
        obs_m2 = re.search(r'"observation"\s*:\s*"([^"]*)', stripped)
        if not obs_m2:
            return None
        observation = obs_m2.group(1)

    out: dict[str, Any] = {"observation": observation}
    plan_m = re.search(r'"plan_status"\s*:\s*"((?:\\.|[^"\\])*)"', stripped)
    if plan_m:
        try:
            out["plan_status"] = json.loads(f'"{plan_m.group(1)}"')
        except json.JSONDecodeError:
            out["plan_status"] = plan_m.group(1)
    return out


def parse_tool_arguments(raw: str | dict[str, Any]) -> dict[str, Any]:
    """
    解析 tool_calls function.arguments 为 dict。

    流式聚合偶发尾部多余字符或字符串内未转义引号，依次尝试：
    raw_decode → 引号修复 → parse_llm_json_object。
    """
    if isinstance(raw, dict):
        return _coerce_nested_json_strings(raw)
    text = str(raw or "{}").strip()
    if not text:
        return {}
    candidates = [text]
    if not text.startswith("{"):
        brace = re.search(r"\{[\s\S]*\}", text)
        if brace:
            candidates.append(brace.group(0))
    repaired = repair_json_string_literals(text)
    if repaired != text:
        candidates.append(repaired)
        brace = re.search(r"\{[\s\S]*\}", repaired)
        if brace and brace.group(0) not in candidates:
            candidates.append(brace.group(0))

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            data, end = json.JSONDecoder().raw_decode(candidate)
        except json.JSONDecodeError as e:
            last_error = e
            continue
        if isinstance(data, dict):
            if end < len(candidate):
                tail = candidate[end:].strip()
                if tail and not set(tail) <= set("{}[], \t\n\r"):
                    continue
            return _coerce_nested_json_strings(data)
        last_error = ValueError("响应必须是 JSON 对象")

    try:
        data = parse_llm_json_object(text)
        if isinstance(data, dict):
            return _coerce_nested_json_strings(data)
    except ValueError as e:
        last_error = e

    salvaged = salvage_truncated_tool_arguments(text)
    if salvaged is not None:
        return _coerce_nested_json_strings(salvaged)

    detail = str(last_error) if last_error else "无法解析"
    raise ValueError(f"LLM 返回非合法 JSON: {detail}: {text[:200]}")
