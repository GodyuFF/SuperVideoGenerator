"""事件总线：将编排层事件分发给 WebSocket 等订阅者。"""

from typing import Any, Callable, Awaitable

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class EventEmitter:
    """简单的异步事件发布/订阅器。"""

    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> None:
        """注册事件处理器（如 WebSocket 广播）。"""
        self._handlers.append(handler)

    async def emit(self, event: dict[str, Any]) -> None:
        """向所有订阅者广播事件字典。"""
        for handler in self._handlers:
            await handler(event)

    async def emit_model(self, model: Any) -> None:
        """将 Pydantic 模型序列化后广播。"""
        if hasattr(model, "model_dump"):
            await self.emit(model.model_dump())
        else:
            await self.emit(dict(model))
