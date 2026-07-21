"""A2UI 确认管理器：挂起异步等待，直至 WebSocket 收到用户响应或超时。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

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

ResolveReason = Literal["expired", "already_resolved", "unknown"]


@dataclass(frozen=True)
class ResolveResult:
    """WebSocket resolve 结果：是否唤醒挂起 Future，以及失败原因。"""

    resolved: bool
    reason: ResolveReason | None = None


class ConfirmationTimeoutError(Exception):
    """用户未在时限内完成 A2UI 确认。"""

    def __init__(self, confirmation_id: str) -> None:
        self.confirmation_id = confirmation_id
        super().__init__("用户确认超时，未收到回答")


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
        self._expired_ids: set[str] = set()

    def has_pending(self) -> bool:
        """是否存在尚未 resolve 的 A2UI 确认。"""
        return bool(self._pending)

    def set_sqlite_store(self, sqlite_store: ConversationSqliteStore) -> None:
        """注入或替换 SQLite 持久化仓储。"""
        self._sqlite = sqlite_store

    async def _emit_execution_paused(
        self,
        request: A2UIConfirmationRequest,
        *,
        conversation_id: str | None,
    ) -> None:
        """推送执行暂停事件。"""
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
        """推送执行恢复事件。"""
        await self._emitter.emit(
            {
                "type": "execution_resumed",
                "confirmation_id": confirmation_id,
                "conversation_id": conversation_id,
            }
        )

    async def _emit_confirmation_expired(
        self,
        confirmation_id: str,
        *,
        conversation_id: str | None = None,
    ) -> None:
        """推送确认过期事件，供前端将卡片标为不可提交。"""
        await self._emitter.emit(
            {
                "type": "a2ui_confirmation_expired",
                "confirmation_id": confirmation_id,
                "conversation_id": conversation_id,
            }
        )

    def _effective_timeout(self, timeout: float | None) -> float | None:
        """合并调用方 timeout 与默认超时。"""
        if timeout is not None:
            return timeout
        return self._default_timeout

    def _persist_expired(self, confirmation_id: str) -> None:
        """将超时确认写入 SQLite，避免刷新后仍显示 pending。"""
        if not self._sqlite:
            return
        self._sqlite.resolve_a2ui(
            A2UIConfirmationResponse(
                confirmation_id=confirmation_id,
                approved=False,
                values={"intent": "expired"},
            )
        )

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
        self._expired_ids.discard(request.confirmation_id)

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
                self._expired_ids.add(request.confirmation_id)
                self._persist_expired(request.confirmation_id)
                await self._emit_confirmation_expired(
                    request.confirmation_id,
                    conversation_id=conversation_id,
                )
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

    def resolve(self, response: A2UIConfirmationResponse) -> ResolveResult:
        """WebSocket 收到用户响应时调用，唤醒等待中的 Future。"""
        future = self._pending.get(response.confirmation_id)
        if future is None or future.done():
            if response.confirmation_id in self._expired_ids:
                return ResolveResult(resolved=False, reason="expired")
            return ResolveResult(resolved=False, reason="already_resolved")

        if self._sqlite:
            self._sqlite.resolve_a2ui(response)
        future.set_result(response)
        self._pending.pop(response.confirmation_id, None)
        self._expired_ids.discard(response.confirmation_id)
        return ResolveResult(resolved=True)

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
        default_duration_sec: int = 60,
        default_style_mode: str = "storybook",
    ) -> A2UIConfirmationResponse:
        """
        当用户输入不明确时，主动询问剧本需求（AskUserQuestion）。
        收集时长、风格、核心人物/场景等信息；字段须由前端按可编辑表单渲染。
        """
        duration_value = (
            default_duration_sec if isinstance(default_duration_sec, int) and default_duration_sec > 0 else 60
        )
        style_value = (default_style_mode or "storybook").strip() or "storybook"
        components = [
            A2UIComponent(
                id="duration_sec",
                component="text",
                label="目标时长（秒）",
                value=duration_value,
                required=True,
            ),
            A2UIComponent(
                id="style_mode",
                component="select",
                label="视频风格",
                value=style_value,
                options=[
                    {"label": "故事书", "value": "storybook"},
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
        kind: str | None = None,
    ) -> A2UIConfirmationResponse:
        """Agent ask_user_question 工具：动态表单收集用户回答。"""
        from core.llm.tools.shared.ask_user import _questions_to_components

        components = _questions_to_components(list(questions or []))
        if not components:
            raise ValueError("questions 不能为空")
        resolved_kind = (kind or "").strip() or A2UIConfirmationKind.GENERIC
        if resolved_kind not in (
            A2UIConfirmationKind.GENERIC,
            A2UIConfirmationKind.PLAN_APPROVAL,
            "generic",
            "plan_approval",
        ):
            resolved_kind = A2UIConfirmationKind.GENERIC
        response = await self.request(
            kind=resolved_kind,
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
