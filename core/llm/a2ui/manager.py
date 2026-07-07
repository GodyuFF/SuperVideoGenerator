"""A2UI 确认管理器：挂起异步等待，直至 WebSocket 收到用户响应或超时。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from core.llm.a2ui.schemas import (
    A2UIComponent,
    A2UIConfirmationKind,
    A2UIConfirmationRequest,
    A2UIConfirmationResponse,
)
from core.events.emitter import EventEmitter
from core.logging.setup import get_logger, log_stage

if TYPE_CHECKING:
    from core.conversation.sqlite_store import ConversationSqliteStore

logger = get_logger("core.a2ui")


class ConfirmationTimeoutError(Exception):
    """用户未在时限内完成 A2UI 确认。"""


class ConfirmationRejectedError(Exception):
    """用户明确拒绝确认（如拒绝视频生成费用）。"""


class ConfirmationManager:
    """通过 EventEmitter 推送 A2UI 请求，并异步等待前端 WebSocket 回传。"""

    def __init__(
        self,
        emitter: EventEmitter,
        default_timeout: float | None = None,
        *,
        sqlite_store: ConversationSqliteStore | None = None,
    ) -> None:
        self._emitter = emitter
        # None 表示无限等待，直至用户通过 WebSocket 提交确认
        self._default_timeout = default_timeout
        self._sqlite = sqlite_store
        self._pending: dict[str, asyncio.Future[A2UIConfirmationResponse]] = {}

    def has_pending(self) -> bool:
        """是否存在尚未 resolve 的 A2UI 确认。"""
        return bool(self._pending)

    def set_sqlite_store(self, sqlite_store: ConversationSqliteStore) -> None:
        self._sqlite = sqlite_store

    async def _emit_execution_paused(
        self,
        request: A2UIConfirmationRequest,
        *,
        conversation_id: str | None,
    ) -> None:
        await self._emitter.emit(
            {
                "type": "execution_paused",
                "confirmation_id": request.confirmation_id,
                "kind": request.kind,
                "conversation_id": conversation_id,
                "step_id": request.step_id,
            }
        )

    async def _emit_execution_resumed(
        self,
        confirmation_id: str,
        *,
        conversation_id: str | None = None,
    ) -> None:
        await self._emitter.emit(
            {
                "type": "execution_resumed",
                "confirmation_id": confirmation_id,
                "conversation_id": conversation_id,
            }
        )

    def _effective_timeout(self, timeout: float | None) -> float | None:
        if timeout is not None:
            return timeout
        return self._default_timeout

    async def request(
        self,
        kind: str,
        title: str,
        description: str = "",
        components: list[A2UIComponent] | None = None,
        estimated_cost_usd: float | None = None,
        step_id: str | None = None,
        timeout: float | None = None,
        *,
        conversation_id: str | None = None,
    ) -> A2UIConfirmationResponse:
        """发起一次 A2UI 确认并阻塞等待用户响应。"""
        effective_timeout = self._effective_timeout(timeout)
        expires_in_sec = (
            int(effective_timeout) if effective_timeout is not None else None
        )
        request = A2UIConfirmationRequest(
            kind=kind,
            title=title,
            description=description,
            components=components or [],
            estimated_cost_usd=estimated_cost_usd,
            step_id=step_id,
            expires_in_sec=expires_in_sec,
        )
        loop = asyncio.get_event_loop()
        future: asyncio.Future[A2UIConfirmationResponse] = loop.create_future()
        self._pending[request.confirmation_id] = future

        if self._sqlite and conversation_id:
            self._sqlite.append_a2ui_request(conversation_id, request)

        log_stage(
            logger,
            "a2ui",
            "已发起确认请求",
            confirmation_id=request.confirmation_id,
            kind=kind,
            waiting=True,
        )
        await self._emit_execution_paused(request, conversation_id=conversation_id)
        await self._emitter.emit_model(request)

        if effective_timeout is None:
            response = await future
        else:
            try:
                response = await asyncio.wait_for(future, timeout=effective_timeout)
            except asyncio.TimeoutError:
                self._pending.pop(request.confirmation_id, None)
                await self._emit_execution_resumed(
                    request.confirmation_id,
                    conversation_id=conversation_id,
                )
                log_stage(
                    logger,
                    "a2ui",
                    "确认超时",
                    confirmation_id=request.confirmation_id,
                )
                raise ConfirmationTimeoutError(request.confirmation_id)

        await self._emit_execution_resumed(
            request.confirmation_id,
            conversation_id=conversation_id,
        )
        log_stage(
            logger,
            "a2ui",
            "确认已处理",
            confirmation_id=request.confirmation_id,
            approved=response.approved,
        )
        return response

    def resolve(self, response: A2UIConfirmationResponse) -> bool:
        """WebSocket 收到用户响应时调用，唤醒等待中的 Future。"""
        if self._sqlite:
            self._sqlite.resolve_a2ui(response)
        future = self._pending.get(response.confirmation_id)
        if future is None or future.done():
            return False
        future.set_result(response)
        self._pending.pop(response.confirmation_id, None)
        return True

    def cancel_all_pending(self) -> int:
        """中止执行时唤醒所有挂起确认（视为用户拒绝）。"""
        count = 0
        for conf_id, future in list(self._pending.items()):
            if future.done():
                self._pending.pop(conf_id, None)
                continue
            future.set_result(
                A2UIConfirmationResponse(
                    confirmation_id=conf_id,
                    approved=False,
                    values={"intent": "abort"},
                )
            )
            self._pending.pop(conf_id, None)
            count += 1
        return count

    async def request_script_requirements(
        self,
        script_id: str,
        initial_message: str = "",
        timeout: float | None = None,
        *,
        conversation_id: str | None = None,
    ) -> A2UIConfirmationResponse:
        """
        当用户输入不明确时，主动询问剧本需求（AskUserQuestion）。
        收集时长、风格、核心人物/场景等信息。
        """
        components = [
            A2UIComponent(
                id="duration_sec",
                component="text",
                label="目标时长（秒）",
                value=60,
                required=True,
            ),
            A2UIComponent(
                id="style_mode",
                component="select",
                label="视频风格",
                value="dynamic_image",
                options=[
                    {"label": "动态图文", "value": "dynamic_image"},
                    {"label": "动态漫画", "value": "dynamic_comic"},
                    {"label": "AI 视频", "value": "ai_video"},
                ],
                required=True,
            ),
            A2UIComponent(
                id="main_characters",
                component="text",
                label="核心人物/角色描述",
                value="",
            ),
            A2UIComponent(
                id="main_scenes",
                component="text",
                label="核心场景描述",
                value="",
            ),
            A2UIComponent(
                id="theme",
                component="text",
                label="视频主题/创意描述",
                value=initial_message,
                required=True,
            ),
        ]
        response = await self.request(
            kind=A2UIConfirmationKind.SCRIPT_REQUIREMENTS,
            title="请补充剧本需求",
            description="为了生成符合您预期的视频，请填写以下信息：",
            components=components,
            step_id=script_id,
            timeout=timeout,
            conversation_id=conversation_id,
        )
        if not response.approved:
            raise ConfirmationRejectedError(script_id)
        return response

    async def request_user_questions(
        self,
        *,
        title: str,
        description: str = "",
        questions: list[dict[str, Any]] | None = None,
        step_id: str | None = None,
        timeout: float | None = None,
        conversation_id: str | None = None,
    ) -> A2UIConfirmationResponse:
        """Agent ask_user_question 工具：动态表单收集用户回答。"""
        from core.llm.tools.shared.ask_user import _questions_to_components

        components = _questions_to_components(list(questions or []))
        if not components:
            raise ValueError("questions 不能为空")
        response = await self.request(
            kind=A2UIConfirmationKind.GENERIC,
            title=title,
            description=description,
            components=components,
            step_id=step_id,
            timeout=timeout,
            conversation_id=conversation_id,
        )
        if not response.approved:
            raise ConfirmationRejectedError(step_id or title)
        return response
