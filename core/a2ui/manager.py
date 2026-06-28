"""A2UI 确认管理器：挂起异步等待，直至 WebSocket 收到用户响应或超时。"""

import asyncio

from core.a2ui.schemas import (
    A2UIComponent,
    A2UIConfirmationKind,
    A2UIConfirmationRequest,
    A2UIConfirmationResponse,
)
from core.events.emitter import EventEmitter
from core.logging.setup import get_logger, log_stage

logger = get_logger("core.a2ui")


class ConfirmationTimeoutError(Exception):
    """用户未在时限内完成 A2UI 确认。"""


class ConfirmationRejectedError(Exception):
    """用户明确拒绝确认（如拒绝视频生成费用）。"""


class ConfirmationManager:
    """通过 EventEmitter 推送 A2UI 请求，并异步等待前端 WebSocket 回传。"""

    def __init__(self, emitter: EventEmitter, default_timeout: float = 300.0) -> None:
        self._emitter = emitter
        self._default_timeout = default_timeout
        # 待处理的确认：confirmation_id -> Future
        self._pending: dict[str, asyncio.Future[A2UIConfirmationResponse]] = {}

    async def request(
        self,
        kind: str,
        title: str,
        description: str = "",
        components: list[A2UIComponent] | None = None,
        estimated_cost_usd: float | None = None,
        step_id: str | None = None,
        timeout: float | None = None,
    ) -> A2UIConfirmationResponse:
        """发起一次 A2UI 确认并阻塞等待用户响应。"""
        request = A2UIConfirmationRequest(
            kind=kind,
            title=title,
            description=description,
            components=components or [],
            estimated_cost_usd=estimated_cost_usd,
            step_id=step_id,
            expires_in_sec=int(timeout or self._default_timeout),
        )
        loop = asyncio.get_event_loop()
        future: asyncio.Future[A2UIConfirmationResponse] = loop.create_future()
        self._pending[request.confirmation_id] = future

        log_stage(
            logger,
            "a2ui",
            "已发起确认请求",
            confirmation_id=request.confirmation_id,
            kind=kind,
            waiting=True,
        )
        await self._emitter.emit_model(request)

        try:
            response = await asyncio.wait_for(
                future, timeout=timeout or self._default_timeout
            )
        except asyncio.TimeoutError:
            self._pending.pop(request.confirmation_id, None)
            log_stage(
                logger,
                "a2ui",
                "确认超时",
                confirmation_id=request.confirmation_id,
            )
            raise ConfirmationTimeoutError(request.confirmation_id)

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
        future = self._pending.get(response.confirmation_id)
        if future is None or future.done():
            return False
        future.set_result(response)
        self._pending.pop(response.confirmation_id, None)
        return True

    async def request_script_requirements(
        self,
        script_id: str,
        initial_message: str = "",
        timeout: float | None = None,
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
                    {"label": "动态图片", "value": "dynamic_image"},
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
        )
        if not response.approved:
            raise ConfirmationRejectedError(script_id)
        return response
