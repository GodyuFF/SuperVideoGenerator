"""Anthropic Messages API 客户端（DeepSeek / Anthropic）。"""

import time
from collections.abc import Callable
from typing import Any

import httpx

from core.execution.cancel import ExecutionCancelledError

from core.interaction_log.models import InteractionRecord
from core.interaction_log.redact import redact_for_log, redact_headers
from core.interaction_log.recorder import InteractionRecorder
from core.llm.client.errors import format_llm_http_error
from core.llm.client.settings import LLMConfigManager
from core.llm.streaming import OnDelta, ToolCallAccumulator, parse_sse_line
from core.llm.json_parse import parse_llm_json_object
from core.llm.client.finish_reason import (
    LlmOutputTruncatedError,
    describe_finish_reason,
    is_output_truncated,
    normalize_finish_reason,
)
from core.llm.client.token_round import TokenRoundAccumulator
from core.llm.client.tokens import (
    TokenBreakdown,
    build_token_usage_meta,
    estimate_request_breakdown,
    normalize_api_usage,
)
from core.llm.client.tool_calls import ToolCallResult
from core.llm.model.llm_request import LlmRequest
from core.llm.client.wire import (
    llm_request_to_anthropic_payload,
    llm_request_to_log_body,
    llm_request_to_wire_messages,
)
from core.logging.setup import get_logger, log_stage

logger = get_logger("core.llm.client")

_TOOL_CALLS_RETRY_USER = (
    "上一轮 assistant 回复未包含 tool_use。"
    "禁止仅用 content 与用户闲聊、自我介绍或重复提问；"
    "必须通过 tool_use 调用且只能调用一个 available_actions 中的工具。"
    "若用户诉求不明确，请调用 ask_user_question 收集信息。"
)

ANTHROPIC_VERSION = "2023-06-01"


def _raise_if_aborted(should_abort: Callable[[], bool] | None) -> None:
    if should_abort and should_abort():
        raise ExecutionCancelledError()


def _anthropic_headers(api_key: str) -> dict[str, str]:
    return {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "Content-Type": "application/json",
    }


def _messages_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/v1/messages"


def _estimate_request_breakdown(request: LlmRequest, max_tokens: int) -> TokenBreakdown:
    return estimate_request_breakdown(request, max_tokens)


def _build_estimated_token_meta(
    request: LlmRequest,
    max_tokens: int,
    *,
    finish_reason: str | None = None,
    stream_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    breakdown = _estimate_request_breakdown(request, max_tokens)
    actual = normalize_api_usage((stream_meta or {}).get("usage"))
    fr = finish_reason or (stream_meta or {}).get("finish_reason")
    normalized = normalize_finish_reason(fr) if fr else None
    truncated = is_output_truncated(fr) if fr else None
    meta = build_token_usage_meta(
        breakdown,
        estimated=actual is None,
        actual_usage=actual,
        finish_reason=fr,
        finish_reason_normalized=normalized or None,
        truncated=truncated,
    )
    if truncated:
        meta["abort_reason"] = describe_finish_reason(
            fr,
            output_tokens=(actual or {}).get("completion_tokens"),
            max_tokens=max_tokens,
        )
    return meta


def _merge_response_token_meta(
    request: LlmRequest,
    max_tokens: int,
    stream_meta: dict[str, Any],
    *,
    fallback_meta: dict[str, Any],
) -> dict[str, Any]:
    meta = _build_estimated_token_meta(
        request,
        max_tokens,
        finish_reason=stream_meta.get("finish_reason"),
        stream_meta=stream_meta,
    )
    if not meta.get("actual_usage") and fallback_meta:
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "estimated"):
            if key in fallback_meta and key not in meta:
                meta[key] = fallback_meta[key]
    return meta


def _tool_calls_retry_request(
    request: LlmRequest, assistant_content: str
) -> LlmRequest:
    from core.llm.model.chat_message import chat_message

    messages = list(request.messages)
    if assistant_content.strip():
        messages.append(chat_message("assistant", assistant_content))
    messages.append(chat_message("user", _TOOL_CALLS_RETRY_USER))
    return LlmRequest(
        system=request.system,
        tools=list(request.tools),
        messages=messages,
        tool_choice=request.tool_choice,
    )


def _tool_calls_response_log_body(
    result: ToolCallResult, stream_meta: dict[str, Any], *, max_tokens: int = 0
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "assistant_message": dict(result.raw_message),
        "content": result.content,
        "tool_calls": result.tool_calls,
    }
    finish_reason = stream_meta.get("finish_reason")
    if finish_reason:
        body["finish_reason"] = finish_reason
        body["finish_reason_normalized"] = normalize_finish_reason(finish_reason)
        if is_output_truncated(finish_reason):
            body["truncated"] = True
            usage = normalize_api_usage(stream_meta.get("usage"))
            body["abort_reason"] = describe_finish_reason(
                finish_reason,
                output_tokens=(usage or {}).get("completion_tokens"),
                max_tokens=max_tokens or None,
            )
    if stream_meta.get("usage"):
        body["usage"] = stream_meta["usage"]
    if stream_meta.get("response_id"):
        body["response_id"] = stream_meta["response_id"]
    return body


class LLMClient:
    """Anthropic Messages API 客户端：仅负责 HTTP 流式调用与响应解析。"""

    def __init__(
        self,
        config: LLMConfigManager,
        recorder: InteractionRecorder | None = None,
    ) -> None:
        self._config = config
        self._recorder = recorder
        self._token_round: TokenRoundAccumulator | None = None

    def begin_token_round(
        self,
        *,
        conversation_id: str,
        project_id: str,
        script_id: str,
    ) -> None:
        self._token_round = TokenRoundAccumulator(
            conversation_id=conversation_id,
            project_id=project_id,
            script_id=script_id,
        )

    def end_token_round(self) -> dict[str, Any] | None:
        if not self._token_round:
            return None
        snapshot = self._token_round.snapshot()
        self._token_round = None
        return snapshot

    def _client_kwargs(self) -> dict[str, Any]:
        settings = self._config.get_settings()
        return {
            "timeout": settings.timeout_sec,
            "trust_env": settings.trust_env,
        }

    def _adapt_request_tool_choice(self, request: LlmRequest) -> LlmRequest:
        adapted = self._config.adapt_tool_choice(request.tool_choice)
        if adapted is request.tool_choice:
            return request
        return request.model_copy(update={"tool_choice": adapted})

    async def _stream_messages(
        self,
        request: LlmRequest,
        *,
        log_context: dict[str, Any],
        summary_prefix: str,
        url: str,
        model: str,
        settings: Any,
        headers: dict[str, str],
        on_delta: OnDelta | None = None,
        response_kind: str = "text",
        should_abort: Callable[[], bool] | None = None,
    ) -> str:
        """流式调用 Messages API，返回完整文本。"""
        ctx = log_context
        breakdown = _estimate_request_breakdown(request, settings.max_tokens)
        token_meta = _build_estimated_token_meta(request, settings.max_tokens)
        if self._token_round:
            from core.llm.client.tokens import TokenEstimate

            self._token_round.add(
                settings.provider,
                model,
                TokenEstimate(
                    breakdown.system_tokens
                    + breakdown.tools_tokens
                    + breakdown.messages_tokens,
                    breakdown.completion_budget_tokens,
                    breakdown.total_estimated_tokens,
                ),
                breakdown=breakdown,
                kind=response_kind,
                agent_name=str(ctx.get("agent_name", "")),
            )

        payload = llm_request_to_anthropic_payload(
            request,
            model=model,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            stream=True,
        )
        log_payload = llm_request_to_log_body(
            request,
            model=model,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            stream=True,
        )

        log_stage(
            logger,
            "llm.request",
            f"{summary_prefix} 流式请求",
            provider=settings.provider,
            model=model,
        )

        if self._recorder:
            await self._recorder.record(
                InteractionRecord(
                    kind="llm_request",
                    source="llm",
                    project_id=str(ctx.get("project_id", "")),
                    script_id=str(ctx.get("script_id", "")),
                    agent_name=str(ctx.get("agent_name", "")),
                    step_id=str(ctx.get("step_id", "")),
                    provider=settings.provider,
                    model=model,
                    method="POST",
                    url=url,
                    summary=f"{summary_prefix} 流式 → {settings.provider}/{model}",
                    request_body=redact_for_log(log_payload),
                    meta={
                        "role": ctx.get("role", ""),
                        "iteration": ctx.get("iteration"),
                        "action": ctx.get("action", ""),
                        "stream": True,
                        "conversation_id": ctx.get("conversation_id", ""),
                        "token_usage": token_meta,
                    },
                )
            )

        start = time.perf_counter()
        parts: list[str] = []
        stream_meta: dict[str, Any] = {}
        try:
            async with httpx.AsyncClient(**self._client_kwargs()) as client:
                async with client.stream(
                    "POST", url, headers=headers, json=payload
                ) as resp:
                    if resp.status_code >= 400:
                        body = await resp.aread()
                        duration_ms = (time.perf_counter() - start) * 1000
                        err_text = body.decode("utf-8", errors="replace")[:500]
                        if self._recorder:
                            await self._recorder.record(
                                InteractionRecord(
                                    kind="llm_error",
                                    source="llm",
                                    project_id=str(ctx.get("project_id", "")),
                                    script_id=str(ctx.get("script_id", "")),
                                    agent_name=str(ctx.get("agent_name", "")),
                                    step_id=str(ctx.get("step_id", "")),
                                    provider=settings.provider,
                                    model=model,
                                    method="POST",
                                    url=url,
                                    status_code=resp.status_code,
                                    duration_ms=duration_ms,
                                    summary=f"LLM 错误 {resp.status_code}",
                                    request_body=redact_for_log(log_payload),
                                    response_body=err_text[:4000],
                                    error=err_text,
                                )
                            )
                        raise RuntimeError(
                            f"LLM API 错误 {resp.status_code}: {err_text}"
                        )

                    async for line in resp.aiter_lines():
                        _raise_if_aborted(should_abort)
                        delta, meta = parse_sse_line(line)
                        if meta:
                            if meta.get("usage"):
                                stream_meta["usage"] = meta["usage"]
                            if meta.get("finish_reason"):
                                stream_meta["finish_reason"] = meta["finish_reason"]
                            if meta.get("response_id"):
                                stream_meta["response_id"] = meta["response_id"]
                        if delta is None or "content" not in delta:
                            continue
                        text = str(delta["content"])
                        if not text:
                            continue
                        parts.append(text)
                        if on_delta:
                            await on_delta(text)

                    duration_ms = (time.perf_counter() - start) * 1000
                    content = "".join(parts)
                    if not content:
                        raise RuntimeError("LLM 返回空内容")

                    response_token_meta = _merge_response_token_meta(
                        request,
                        settings.max_tokens,
                        stream_meta,
                        fallback_meta=token_meta,
                    )
                    finish_reason = stream_meta.get("finish_reason")
                    if is_output_truncated(finish_reason):
                        usage = normalize_api_usage(stream_meta.get("usage"))
                        raise LlmOutputTruncatedError(
                            finish_reason,
                            output_tokens=(usage or {}).get("completion_tokens"),
                            max_tokens=settings.max_tokens,
                        )

                    log_stage(
                        logger,
                        "llm.response",
                        f"{summary_prefix} 流式响应",
                        length=len(content),
                    )
                    if self._recorder:
                        await self._recorder.record(
                            InteractionRecord(
                                kind="llm_response",
                                source="llm",
                                project_id=str(ctx.get("project_id", "")),
                                script_id=str(ctx.get("script_id", "")),
                                agent_name=str(ctx.get("agent_name", "")),
                                step_id=str(ctx.get("step_id", "")),
                                provider=settings.provider,
                                model=model,
                                method="POST",
                                url=url,
                                status_code=resp.status_code,
                                duration_ms=duration_ms,
                                summary=f"{summary_prefix} 流式响应 {len(content)} 字符",
                                request_body=redact_for_log(log_payload),
                                response_body=redact_for_log(
                                    {
                                        "content": content,
                                        "finish_reason": finish_reason,
                                        "finish_reason_normalized": (
                                            normalize_finish_reason(finish_reason)
                                            if finish_reason
                                            else None
                                        ),
                                        "headers": redact_headers(
                                            dict(resp.headers)
                                        ),
                                    }
                                ),
                                meta={
                                    "stream": True,
                                    "response_kind": response_kind,
                                    "conversation_id": ctx.get("conversation_id", ""),
                                    "token_usage": response_token_meta,
                                    "finish_reason": finish_reason,
                                    "truncated": is_output_truncated(finish_reason)
                                    if finish_reason
                                    else False,
                                },
                            )
                        )
                    return content
        except httpx.HTTPError as e:
            duration_ms = (time.perf_counter() - start) * 1000
            if self._recorder:
                await self._recorder.record(
                    InteractionRecord(
                        kind="llm_error",
                        source="llm",
                        project_id=str(ctx.get("project_id", "")),
                        script_id=str(ctx.get("script_id", "")),
                        agent_name=str(ctx.get("agent_name", "")),
                        step_id=str(ctx.get("step_id", "")),
                        provider=settings.provider,
                        model=model,
                        method="POST",
                        url=url,
                        duration_ms=duration_ms,
                        summary="LLM 网络错误",
                        request_body=redact_for_log(log_payload),
                        error=str(e),
                    )
                )
            raise RuntimeError(
                format_llm_http_error(e, url=url, provider=settings.provider)
            ) from e

    async def complete(
        self,
        request: LlmRequest,
        *,
        log_context: dict[str, Any] | None = None,
        summary_prefix: str = "LLM",
        on_delta: OnDelta | None = None,
        response_format: dict[str, Any] | None = None,
        response_kind: str = "text",
        should_abort: Callable[[], bool] | None = None,
    ) -> str:
        """流式 Messages API，返回 assistant 完整文本。"""
        _ = response_format
        if not request.system.strip() and not request.messages:
            raise ValueError("LlmRequest 不能为空")
        ctx = log_context or {}
        api_key = self._config.resolved_api_key()
        if not api_key:
            raise RuntimeError("未配置 LLM API Key")

        settings = self._config.get_settings()
        url = _messages_url(self._config.resolved_base_url())
        model = self._config.resolved_model()
        headers = _anthropic_headers(api_key)
        request = self._adapt_request_tool_choice(request)

        return await self._stream_messages(
            request,
            log_context=ctx,
            summary_prefix=summary_prefix,
            url=url,
            model=model,
            settings=settings,
            headers=headers,
            on_delta=on_delta,
            response_kind=response_kind,
            should_abort=should_abort,
        )

    async def complete_json(
        self,
        request: LlmRequest,
        *,
        log_context: dict[str, Any] | None = None,
        summary_prefix: str = "LLM JSON",
        on_delta: OnDelta | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """流式 Messages API，解析 JSON 对象响应。"""
        _ = response_format
        ctx = log_context or {}
        content = await self.complete(
            request,
            log_context=ctx,
            summary_prefix=summary_prefix,
            on_delta=on_delta,
            response_kind="json",
        )
        parsed = self._parse_json_content(content)
        log_stage(
            logger,
            "llm.response",
            f"{summary_prefix} JSON 解析",
            keys=list(parsed.keys()),
        )
        return parsed

    @staticmethod
    def _parse_json_content(content: str) -> dict[str, Any]:
        try:
            return parse_llm_json_object(content)
        except ValueError as e:
            raise RuntimeError(str(e)) from e

    async def complete_tool_calls(
        self,
        request: LlmRequest,
        *,
        log_context: dict[str, Any] | None = None,
        summary_prefix: str = "LLM tool_calls",
        on_delta: OnDelta | None = None,
        should_abort: Callable[[], bool] | None = None,
    ) -> ToolCallResult:
        """流式 Messages API，返回 assistant content + tool_calls。"""
        if not request.system.strip() and not request.messages:
            raise ValueError("LlmRequest 不能为空")
        if not request.tools:
            raise ValueError("tools 不能为空")
        ctx = log_context or {}
        api_key = self._config.resolved_api_key()
        if not api_key:
            raise RuntimeError("未配置 LLM API Key")

        settings = self._config.get_settings()
        url = _messages_url(self._config.resolved_base_url())
        model = self._config.resolved_model()
        headers = _anthropic_headers(api_key)

        current_request = self._adapt_request_tool_choice(request)
        last_result: ToolCallResult | None = None

        for attempt in range(2):
            breakdown = _estimate_request_breakdown(current_request, settings.max_tokens)
            token_meta = _build_estimated_token_meta(
                current_request, settings.max_tokens
            )
            if self._token_round and attempt == 0:
                from core.llm.client.tokens import TokenEstimate

                self._token_round.add(
                    settings.provider,
                    model,
                    TokenEstimate(
                        breakdown.system_tokens
                        + breakdown.tools_tokens
                        + breakdown.messages_tokens,
                        breakdown.completion_budget_tokens,
                        breakdown.total_estimated_tokens,
                    ),
                    breakdown=breakdown,
                    kind="tool_calls",
                    agent_name=str(ctx.get("agent_name", "")),
                )

            payload = llm_request_to_anthropic_payload(
                current_request,
                model=model,
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
                stream=True,
            )
            log_payload = llm_request_to_log_body(
                current_request,
                model=model,
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
                stream=True,
                attempt=attempt + 1,
            )

            if attempt == 0:
                log_stage(
                    logger,
                    "llm.request",
                    f"{summary_prefix} 流式 tool_calls",
                    provider=settings.provider,
                    model=model,
                )
                if self._recorder:
                    await self._recorder.record(
                        InteractionRecord(
                            kind="llm_request",
                            source="llm",
                            project_id=str(ctx.get("project_id", "")),
                            script_id=str(ctx.get("script_id", "")),
                            agent_name=str(ctx.get("agent_name", "")),
                            step_id=str(ctx.get("step_id", "")),
                            provider=settings.provider,
                            model=model,
                            method="POST",
                            url=url,
                            summary=f"{summary_prefix} tool_calls → {settings.provider}/{model}",
                            request_body=redact_for_log(log_payload),
                            meta={
                                "role": ctx.get("role", ""),
                                "iteration": ctx.get("iteration"),
                                "action": ctx.get("action", ""),
                                "stream": True,
                                "conversation_id": ctx.get("conversation_id", ""),
                                "token_usage": token_meta,
                            },
                        )
                    )

            start = time.perf_counter()
            accumulator = ToolCallAccumulator()
            content_deltas: list[str] = []
            try:
                async with httpx.AsyncClient(**self._client_kwargs()) as client:
                    async with client.stream(
                        "POST", url, headers=headers, json=payload
                    ) as resp:
                        if resp.status_code >= 400:
                            body = await resp.aread()
                            duration_ms = (time.perf_counter() - start) * 1000
                            err_text = body.decode("utf-8", errors="replace")[:4000]
                            if self._recorder:
                                await self._recorder.record(
                                    InteractionRecord(
                                        kind="llm_error",
                                        source="llm",
                                        project_id=str(ctx.get("project_id", "")),
                                        script_id=str(ctx.get("script_id", "")),
                                        agent_name=str(ctx.get("agent_name", "")),
                                        step_id=str(ctx.get("step_id", "")),
                                        provider=settings.provider,
                                        model=model,
                                        method="POST",
                                        url=url,
                                        status_code=resp.status_code,
                                        duration_ms=duration_ms,
                                        summary=f"LLM tool_calls 错误 {resp.status_code}",
                                        request_body=redact_for_log(log_payload),
                                        response_body=err_text,
                                        error=err_text[:500],
                                        meta={
                                            "stream": True,
                                            "response_kind": "tool_calls",
                                            "attempt": attempt + 1,
                                            "conversation_id": ctx.get("conversation_id", ""),
                                        },
                                    )
                                )
                            raise RuntimeError(
                                f"LLM API 错误 {resp.status_code}: {err_text[:500]}"
                            )

                        async for line in resp.aiter_lines():
                            _raise_if_aborted(should_abort)
                            delta, meta = parse_sse_line(line)
                            if meta:
                                accumulator.absorb_meta(meta)
                            if delta is None:
                                continue
                            content_delta = accumulator.feed(delta)
                            if content_delta:
                                content_deltas.append(content_delta)

                        duration_ms = (time.perf_counter() - start) * 1000
                        result = accumulator.build()
                        last_result = result
                        stream_meta = accumulator.stream_meta()
                        finish_reason = stream_meta.get("finish_reason")
                        has_tools = bool(result.tool_calls)

                        if is_output_truncated(finish_reason):
                            usage = normalize_api_usage(stream_meta.get("usage"))
                            response_token_meta = _merge_response_token_meta(
                                current_request,
                                settings.max_tokens,
                                stream_meta,
                                fallback_meta=token_meta,
                            )
                            response_body = _tool_calls_response_log_body(
                                result,
                                stream_meta,
                                max_tokens=settings.max_tokens,
                            )
                            if self._recorder:
                                await self._recorder.record(
                                    InteractionRecord(
                                        kind="llm_response",
                                        source="llm",
                                        project_id=str(ctx.get("project_id", "")),
                                        script_id=str(ctx.get("script_id", "")),
                                        agent_name=str(ctx.get("agent_name", "")),
                                        step_id=str(ctx.get("step_id", "")),
                                        provider=settings.provider,
                                        model=model,
                                        method="POST",
                                        url=url,
                                        status_code=resp.status_code,
                                        duration_ms=duration_ms,
                                        summary=f"{summary_prefix} 输出截断 abort",
                                        request_body=redact_for_log(log_payload),
                                        response_body=redact_for_log(response_body),
                                        meta={
                                            "stream": True,
                                            "response_kind": "tool_calls",
                                            "tool_calls_present": False,
                                            "attempt": attempt + 1,
                                            "conversation_id": ctx.get(
                                                "conversation_id", ""
                                            ),
                                            "token_usage": response_token_meta,
                                            "finish_reason": finish_reason,
                                            "truncated": True,
                                            "abort_reason": describe_finish_reason(
                                                finish_reason,
                                                output_tokens=(usage or {}).get(
                                                    "completion_tokens"
                                                ),
                                                max_tokens=settings.max_tokens,
                                            ),
                                        },
                                    )
                                )
                            raise LlmOutputTruncatedError(
                                finish_reason,
                                output_tokens=(usage or {}).get("completion_tokens"),
                                max_tokens=settings.max_tokens,
                            )

                        log_stage(
                            logger,
                            "llm.response",
                            f"{summary_prefix} tool_calls 响应",
                            tool=result.primary_name() if has_tools else "none",
                            attempt=attempt + 1,
                        )
                        response_body = _tool_calls_response_log_body(
                            result, stream_meta, max_tokens=settings.max_tokens
                        )
                        response_token_meta = _merge_response_token_meta(
                            current_request,
                            settings.max_tokens,
                            stream_meta,
                            fallback_meta=token_meta,
                        )
                        if self._recorder:
                            await self._recorder.record(
                                InteractionRecord(
                                    kind="llm_response",
                                    source="llm",
                                    project_id=str(ctx.get("project_id", "")),
                                    script_id=str(ctx.get("script_id", "")),
                                    agent_name=str(ctx.get("agent_name", "")),
                                    step_id=str(ctx.get("step_id", "")),
                                    provider=settings.provider,
                                    model=model,
                                    method="POST",
                                    url=url,
                                    status_code=resp.status_code,
                                    duration_ms=duration_ms,
                                    summary=(
                                        f"{summary_prefix} tool_calls "
                                        f"{result.primary_name() if has_tools else 'missing'}"
                                    ),
                                    request_body=redact_for_log(log_payload),
                                    response_body=redact_for_log(response_body),
                                    meta={
                                        "stream": True,
                                        "response_kind": "tool_calls",
                                        "tool_calls_present": has_tools,
                                        "attempt": attempt + 1,
                                        "conversation_id": ctx.get("conversation_id", ""),
                                        "token_usage": response_token_meta,
                                        "finish_reason": finish_reason,
                                        "finish_reason_normalized": (
                                            normalize_finish_reason(finish_reason)
                                            if finish_reason
                                            else None
                                        ),
                                        "truncated": False,
                                    },
                                )
                            )

                        if has_tools:
                            if on_delta:
                                for part in content_deltas:
                                    await on_delta(part)
                            return result

                        if attempt == 0:
                            current_request = self._adapt_request_tool_choice(
                                _tool_calls_retry_request(request, result.content)
                            )
                            continue

                        preview = result.content.strip().replace("\n", " ")[:120]
                        raise RuntimeError(
                            f"LLM 未返回 tool_calls（仅返回文本：{preview or '空'}）"
                        )
            except httpx.HTTPError as e:
                raise RuntimeError(
                    format_llm_http_error(e, url=url, provider=settings.provider)
                ) from e

        preview = (last_result.content if last_result else "").strip()[:120]
        raise RuntimeError(f"LLM 未返回 tool_calls（仅返回文本：{preview or '空'}）")
