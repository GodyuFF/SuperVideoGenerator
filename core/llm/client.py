"""OpenAI 兼容 Chat Completions 客户端（DeepSeek / OpenAI / Kimi 等）。"""

import time
from typing import Any

import httpx

from core.interaction_log.models import InteractionRecord
from core.interaction_log.redact import redact_for_log, redact_headers
from core.interaction_log.recorder import InteractionRecorder
from core.llm.errors import format_llm_http_error
from core.llm.settings import LLMConfigManager
from core.llm.streaming import OnDelta, parse_sse_data_line
from core.llm.token_round import TokenRoundAccumulator
from core.llm.tokens import estimate_chat_tokens
from core.logging.setup import get_logger, log_stage

logger = get_logger("core.llm.client")


class LLMClient:
    """OpenAI 兼容 Chat Completions 客户端（流式文本 / JSON）。"""

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

    async def _stream_chat_completions(
        self,
        messages: list[dict[str, str]],
        payload_extra: dict[str, Any],
        *,
        log_context: dict[str, Any],
        summary_prefix: str,
        url: str,
        model: str,
        settings: Any,
        headers: dict[str, str],
        on_delta: OnDelta | None = None,
        response_kind: str = "text",
    ) -> str:
        """流式调用 Chat Completions，返回完整文本。"""
        ctx = log_context
        estimate = estimate_chat_tokens(messages, settings.max_tokens)
        token_meta = {**estimate.to_dict(), "estimated": True}
        if self._token_round:
            self._token_round.add(
                settings.provider,
                model,
                estimate,
                kind=response_kind,
                agent_name=str(ctx.get("agent_name", "")),
            )

        payload: dict[str, Any] = {
            "model": model,
            "temperature": settings.temperature,
            "max_tokens": settings.max_tokens,
            "messages": messages,
            "stream": True,
            **payload_extra,
        }

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
                    request_body=redact_for_log(payload),
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
                                    request_body=redact_for_log(payload),
                                    response_body=err_text[:4000],
                                    error=err_text,
                                )
                            )
                        raise RuntimeError(
                            f"LLM API 错误 {resp.status_code}: {err_text}"
                        )

                    async for line in resp.aiter_lines():
                        delta = parse_sse_data_line(line)
                        if delta is None:
                            continue
                        parts.append(delta)
                        if on_delta:
                            await on_delta(delta)

                    duration_ms = (time.perf_counter() - start) * 1000
                    content = "".join(parts)
                    if not content:
                        raise RuntimeError("LLM 返回空内容")

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
                                request_body=redact_for_log(payload),
                                response_body=redact_for_log(
                                    {
                                        "content": content,
                                        "headers": redact_headers(
                                            dict(resp.headers)
                                        ),
                                    }
                                ),
                                meta={
                                    "stream": True,
                                    "response_kind": response_kind,
                                    "conversation_id": ctx.get("conversation_id", ""),
                                    "token_usage": token_meta,
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
                        request_body=redact_for_log(payload),
                        error=str(e),
                    )
                )
            raise RuntimeError(
                format_llm_http_error(e, url=url, provider=settings.provider)
            ) from e

    def _build_messages(
        self,
        system_prompt: str,
        user_content: str | None,
        chat_messages: list[dict[str, str]] | None,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]
        if chat_messages:
            messages.extend(chat_messages)
        if user_content is not None:
            messages.append({"role": "user", "content": user_content})
        elif not chat_messages:
            raise ValueError("需要 user_content 或 chat_messages")
        return messages

    async def complete_text(
        self,
        system_prompt: str,
        user_content: str | None = None,
        log_context: dict[str, Any] | None = None,
        summary_prefix: str = "LLM 文本",
        on_delta: OnDelta | None = None,
        response_format: dict[str, Any] | None = None,
        chat_messages: list[dict[str, str]] | None = None,
    ) -> str:
        """流式文本补全，返回完整字符串。"""
        ctx = log_context or {}
        api_key = self._config.resolved_api_key()
        if not api_key:
            raise RuntimeError("未配置 LLM API Key")

        settings = self._config.get_settings()
        url = f"{self._config.resolved_base_url()}/chat/completions"
        model = self._config.resolved_model()
        messages = self._build_messages(system_prompt, user_content, chat_messages)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        extra = {}
        if response_format:
            extra["response_format"] = response_format
        return await self._stream_chat_completions(
            messages,
            extra,
            log_context=ctx,
            summary_prefix=summary_prefix,
            url=url,
            model=model,
            settings=settings,
            headers=headers,
            on_delta=on_delta,
            response_kind="text",
        )

    async def complete_json(
        self,
        system_prompt: str,
        user_content: str | None = None,
        log_context: dict[str, Any] | None = None,
        summary_prefix: str = "LLM JSON",
        on_delta: OnDelta | None = None,
        response_format: dict[str, Any] | None = None,
        chat_messages: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """通用 JSON 补全：流式接收后解析 JSON。"""
        ctx = log_context or {}
        content = await self.complete_text(
            system_prompt,
            user_content,
            log_context=ctx,
            summary_prefix=summary_prefix,
            on_delta=on_delta,
            response_format=response_format,
            chat_messages=chat_messages,
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
        import json
        import re

        text = content.strip()
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if fence:
            text = fence.group(1).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"LLM 返回非合法 JSON: {e}: {content[:200]}") from e
        if not isinstance(data, dict):
            raise RuntimeError("LLM JSON 响应必须是对象")
        return data
