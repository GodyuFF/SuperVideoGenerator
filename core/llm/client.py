"""OpenAI 兼容 Chat Completions 客户端（DeepSeek / OpenAI / Kimi 等）。"""

import time
from typing import Any

import httpx

from core.interaction_log.models import InteractionRecord
from core.interaction_log.redact import redact_for_log, redact_headers
from core.interaction_log.recorder import InteractionRecorder
from core.llm.settings import LLMConfigManager
from core.logging.setup import get_logger, log_stage

logger = get_logger("core.llm.client")


class LLMClient:
    """通过 HTTP 调用大模型，请求与响应均围绕 XML ReAct 协议。"""

    def __init__(
        self,
        config: LLMConfigManager,
        recorder: InteractionRecorder | None = None,
    ) -> None:
        self._config = config
        self._recorder = recorder

    async def complete_xml_react(
        self,
        role_description: str,
        context_xml: str,
        log_context: dict[str, Any] | None = None,
    ) -> str:
        """发送系统提示 + XML 上下文，返回模型原始文本（应含 <react>）。"""
        ctx = log_context or {}
        api_key = self._config.resolved_api_key()
        if not api_key:
            raise RuntimeError("未配置 LLM API Key")

        settings = self._config.get_settings()
        url = f"{self._config.resolved_base_url()}/chat/completions"
        model = self._config.resolved_model()
        messages = [
            {
                "role": "system",
                "content": (
                    f"{role_description}\n\n"
                    "下方用户消息为 XML 格式的 ReAct 上下文，请仅用 XML 的 <react> 块回复。"
                ),
            },
            {"role": "user", "content": context_xml},
        ]
        payload: dict[str, Any] = {
            "model": model,
            "temperature": settings.temperature,
            "max_tokens": settings.max_tokens,
            "messages": messages,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        log_stage(
            logger,
            "llm.request",
            "ReAct XML 请求",
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
                    summary=f"LLM 请求 → {settings.provider}/{model}",
                    request_body=redact_for_log(payload),
                    meta={
                        "role": ctx.get("role", ""),
                        "iteration": ctx.get("iteration"),
                    },
                )
            )

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=settings.timeout_sec) as client:
                resp = await client.post(url, headers=headers, json=payload)
                duration_ms = (time.perf_counter() - start) * 1000
                resp_text = resp.text
                if resp.status_code >= 400:
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
                                response_body=resp_text[:4000],
                                error=resp_text[:500],
                            )
                        )
                    raise RuntimeError(f"LLM API 错误 {resp.status_code}: {resp_text[:500]}")
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content:
                    raise RuntimeError("LLM 返回空内容")
                log_stage(logger, "llm.response", "ReAct XML 响应", length=len(content))
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
                            summary=f"LLM 响应 {len(content)} 字符",
                            request_body=redact_for_log(payload),
                            response_body=redact_for_log(
                                {
                                    "content": content,
                                    "usage": data.get("usage"),
                                    "headers": redact_headers(dict(resp.headers)),
                                }
                            ),
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
            raise
