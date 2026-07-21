"""生图 / 生视频 Provider HTTP 调用的交互日志。"""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Iterator, Literal

import httpx

from core.interaction_log.models import InteractionRecord
from core.interaction_log.redact import redact_for_log, redact_headers

MediaKind = Literal["image", "video"]
MediaPhase = Literal["create", "poll", "edit", "status"]

_RESPONSE_BODY_MAX = 4000
_PROMPT_PREVIEW_MAX = 500


@dataclass
class MediaLogContext:
    """当前生图/生视频调用的编排上下文（由队列/Agent 注入）。"""

    project_id: str = ""
    script_id: str = ""
    agent_name: str = ""
    step_id: str = ""
    asset_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


_media_ctx: ContextVar[MediaLogContext | None] = ContextVar(
    "media_log_context", default=None
)
_recorder_ref: dict[str, Any] = {"recorder": None}


def bind_media_interaction_recorder(recorder: Any | None) -> None:
    """绑定全局 InteractionRecorder（AppState 启动时调用）。"""
    _recorder_ref["recorder"] = recorder


def reset_media_interaction_recorder() -> None:
    """测试用：清空全局 recorder 绑定。"""
    _recorder_ref["recorder"] = None


def get_media_log_context() -> MediaLogContext | None:
    """读取当前媒体日志上下文。"""
    return _media_ctx.get()


@contextmanager
def media_log_scope(
    *,
    project_id: str = "",
    script_id: str = "",
    agent_name: str = "",
    step_id: str = "",
    asset_id: str = "",
    **extra: Any,
) -> Iterator[MediaLogContext]:
    """在生成单项任务期间注入 project/script 等上下文字段。"""
    ctx = MediaLogContext(
        project_id=project_id or "",
        script_id=script_id or "",
        agent_name=agent_name or "",
        step_id=step_id or "",
        asset_id=asset_id or "",
        extra={k: v for k, v in extra.items() if v is not None},
    )
    token: Token = _media_ctx.set(ctx)
    try:
        yield ctx
    finally:
        _media_ctx.reset(token)


def _truncate_response_body(raw: str | dict[str, Any] | None) -> str | dict[str, Any] | None:
    """截断过大响应体，并折叠 base64 字段。"""
    if raw is None:
        return None
    if isinstance(raw, dict):
        out: dict[str, Any] = {}
        for key, val in raw.items():
            kl = str(key).lower()
            if kl in {"b64_json", "image_base64", "data"} and isinstance(val, str) and len(val) > 120:
                out[key] = f"<omitted len={len(val)}>"
            elif isinstance(val, list) and key == "data":
                slim: list[Any] = []
                for item in val[:3]:
                    if isinstance(item, dict):
                        slim.append(_truncate_response_body(item))
                    else:
                        slim.append(item)
                if len(val) > 3:
                    slim.append(f"<+{len(val) - 3} more>")
                out[key] = slim
            elif isinstance(val, (dict, list)):
                out[key] = redact_for_log(val)
            elif isinstance(val, str) and len(val) > _RESPONSE_BODY_MAX:
                out[key] = val[:_RESPONSE_BODY_MAX] + "…"
            else:
                out[key] = val
        return out
    text = str(raw)
    if len(text) > _RESPONSE_BODY_MAX:
        return text[:_RESPONSE_BODY_MAX] + "…"
    return text


def _preview_request_body(body: dict[str, Any] | None) -> dict[str, Any] | None:
    """脱敏并缩短 prompt，便于入库。"""
    if not body:
        return None
    redacted = redact_for_log(body)
    if not isinstance(redacted, dict):
        return {"value": redacted}
    out = dict(redacted)
    for key in ("prompt", "negative_prompt", "text"):
        val = out.get(key)
        if isinstance(val, str) and len(val) > _PROMPT_PREVIEW_MAX:
            out[key] = val[:_PROMPT_PREVIEW_MAX] + "…"
    # 百炼 input.prompt
    inp = out.get("input")
    if isinstance(inp, dict):
        for key in ("prompt", "negative_prompt"):
            val = inp.get(key)
            if isinstance(val, str) and len(val) > _PROMPT_PREVIEW_MAX:
                inp = dict(inp)
                inp[key] = val[:_PROMPT_PREVIEW_MAX] + "…"
                out["input"] = inp
    return out


async def record_media_http(
    *,
    media_kind: MediaKind,
    provider: str,
    model: str = "",
    method: str,
    url: str,
    status_code: int | None,
    duration_ms: float,
    request_body: dict[str, Any] | None = None,
    response_body: str | dict[str, Any] | None = None,
    error: str | None = None,
    phase: MediaPhase = "create",
    headers: dict[str, str] | None = None,
) -> InteractionRecord | None:
    """写入一条媒体 Provider HTTP 交互记录（无 recorder 时静默跳过）。"""
    recorder = _recorder_ref.get("recorder")
    if recorder is None:
        return None
    ctx = get_media_log_context() or MediaLogContext()
    label = "生图" if media_kind == "image" else "生视频"
    status = status_code if status_code is not None else "ERR"
    model_part = f"/{model}" if model else ""
    summary = f"{label} {method} {provider}{model_part} [{phase}] → {status}"
    if error:
        summary = f"{label} {method} {provider}{model_part} [{phase}] 失败：{error[:120]}"
    meta: dict[str, Any] = {
        "media_kind": media_kind,
        "phase": phase,
        "asset_id": ctx.asset_id,
        **(ctx.extra or {}),
    }
    if headers:
        meta["request_headers"] = redact_headers(headers)
    record = InteractionRecord(
        kind="media_http",
        source="media",
        project_id=ctx.project_id,
        script_id=ctx.script_id,
        agent_name=ctx.agent_name,
        step_id=ctx.step_id,
        provider=provider,
        model=model,
        method=method,
        url=url,
        status_code=status_code,
        duration_ms=duration_ms,
        summary=summary,
        request_body=_preview_request_body(request_body),
        response_body=_truncate_response_body(response_body),
        error=error,
        meta=meta,
    )
    return await recorder.record(record)


async def logged_media_request(
    *,
    media_kind: MediaKind,
    provider: str,
    model: str = "",
    method: str = "POST",
    url: str,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = 120.0,
    trust_env: bool = False,
    phase: MediaPhase = "create",
    log_success_response: bool = True,
) -> httpx.Response:
    """
    发起媒体 Provider HTTP 请求并写入交互日志。

    网络异常也会落一条带 error 的记录后重新抛出。
    """
    start = time.perf_counter()
    hdrs = headers or {}
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=trust_env) as client:
            resp = await client.request(
                method,
                url,
                headers=hdrs,
                json=json_body,
                params=params,
            )
    except httpx.HTTPError as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        await record_media_http(
            media_kind=media_kind,
            provider=provider,
            model=model,
            method=method,
            url=url,
            status_code=None,
            duration_ms=duration_ms,
            request_body=json_body,
            error=str(exc),
            phase=phase,
            headers=hdrs,
        )
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    response_body: str | dict[str, Any] | None = None
    err: str | None = None
    if resp.status_code >= 400:
        response_body = resp.text[:_RESPONSE_BODY_MAX]
        err = f"HTTP {resp.status_code}"
    elif log_success_response:
        try:
            response_body = resp.json()
        except ValueError:
            response_body = resp.text[:_RESPONSE_BODY_MAX]
    else:
        response_body = {"omitted": True, "status_code": resp.status_code}

    await record_media_http(
        media_kind=media_kind,
        provider=provider,
        model=model,
        method=method,
        url=url,
        status_code=resp.status_code,
        duration_ms=duration_ms,
        request_body=json_body,
        response_body=response_body,
        error=err,
        phase=phase,
        headers=hdrs,
    )
    return resp
