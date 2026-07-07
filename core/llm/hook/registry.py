"""Hook 注册协议（pre/post tool_call、confirm 网关统一入口）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


class ToolCallHook(Protocol):
    """单条 tool 调用前后扩展。"""

    def before_tool_call(self, action: str, args: dict[str, Any]) -> None: ...

    def after_tool_call(
        self, action: str, args: dict[str, Any], observation: str
    ) -> None: ...


@dataclass
class HookRegistry:
    """主编排 / 子 Agent 共享的 Hook 容器。"""

    tool_call_hooks: list[ToolCallHook] = field(default_factory=list)
    on_confirm_gate: Callable[..., Any] | None = None

    def register_tool_call_hook(self, hook: ToolCallHook) -> None:
        self.tool_call_hooks.append(hook)

    def run_before_tool_call(self, action: str, args: dict[str, Any]) -> None:
        for hook in self.tool_call_hooks:
            hook.before_tool_call(action, args)

    def run_after_tool_call(
        self, action: str, args: dict[str, Any], observation: str
    ) -> None:
        for hook in self.tool_call_hooks:
            hook.after_tool_call(action, args, observation)
