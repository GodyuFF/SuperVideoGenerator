"""MCP 语义 Tool Registry：list_tools / call_tool。"""

from __future__ import annotations

import inspect
from typing import Any

from core.llm.agent.react_core import AgentRunContext
from core.llm.model.llm_request import ToolDefinition
from core.store.memory import MemoryStore
from core.llm.hook.react_guard import (
    EditComposeMissingAssetsError,
    ImageGenerationAbortError,
    TtsAbortError,
)
from core.execution.cancel import ExecutionCancelledError
from core.llm.hook.return_to_master import ReturnToMasterError
from core.llm.model.plan_context import coerce_plan_tracking_arguments
from core.llm.tools.result import ToolResult
from core.llm.tools.spec import ToolKind, ToolSpec
from core.llm.tools.validators import validate_against_schema


class ToolRegistry:
    """单源 tool 注册表。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool 已注册：{spec.name}")
        self._tools[spec.name] = spec

    def register_many(self, specs: list[ToolSpec]) -> None:
        """批量注册 tool。"""
        for spec in specs:
            self.register(spec)

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def list_tools(
        self,
        agent: str | None = None,
        *,
        sources: set[str] | None = None,
    ) -> list[ToolSpec]:
        specs = list(self._tools.values())
        if agent:
            specs = [s for s in specs if s.agent == agent]
        if sources is not None:
            specs = [s for s in specs if s.source in sources]
        return sorted(specs, key=lambda s: s.name)

    def input_schema(self, name: str) -> dict[str, Any]:
        spec = self._tools.get(name)
        if spec is None:
            from core.llm.tools.schemas import action_input_schema

            return action_input_schema(name)
        return dict(spec.input_schema)

    def output_schema(self, name: str) -> dict[str, Any]:
        spec = self._tools.get(name)
        return dict(spec.output_schema) if spec else {}

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        ctx: AgentRunContext,
        store: MemoryStore,
    ) -> ToolResult:
        spec = self._tools.get(name)
        if spec is None:
            return ToolResult(
                observation=f"未知 tool：{name}",
                structured={"error": f"unknown tool {name}", "valid": False},
                ok=False,
            )
        arguments = coerce_plan_tracking_arguments(dict(arguments))
        try:
            validate_against_schema(
                arguments, spec.input_schema, label="输入", tool_name=name
            )
        except ValueError as e:
            return ToolResult(
                observation=str(e),
                structured={"error": str(e), "valid": False},
                ok=False,
            )
        before_outputs = len(ctx.outputs)
        try:
            result = spec.handler(store, ctx, arguments)
            if inspect.isawaitable(result):
                result = await result
        except ImageGenerationAbortError:
            raise
        except ExecutionCancelledError:
            raise
        except ReturnToMasterError:
            raise
        except EditComposeMissingAssetsError:
            raise
        except TtsAbortError:
            raise
        except Exception as e:
            return ToolResult(
                observation=f"执行 {name} 失败：{e}",
                structured={"error": str(e), "valid": False, "action": name},
                ok=False,
            )
        if len(ctx.outputs) < before_outputs + len(result.outputs):
            ctx.outputs.extend(result.outputs)
        if spec.output_schema and result.ok:
            try:
                validate_against_schema(
                    result.structured,
                    spec.output_schema,
                    label="输出",
                    tool_name=name,
                )
            except ValueError as e:
                return ToolResult(
                    observation=str(e),
                    structured={"error": str(e), "valid": False},
                    ok=False,
                )
        return result

    def build_tool_definitions(
        self,
        action_names: list[str],
        *,
        use_full_input_schema: bool = False,
        kind_override: dict[str, str] | None = None,
    ) -> list[ToolDefinition]:
        """组装 LLM tools 列表（Anthropic wire 仅发送 input_schema）。"""
        tools: list[ToolDefinition] = []
        for name in action_names:
            spec = self._tools.get(name)
            if spec:
                description = spec.description
                input_schema = dict(spec.input_schema)
                output_schema = dict(spec.output_schema)
                tool_kind = "function"
                agent_name = ""
            else:
                from core.llm.prompt.tools.registry import _sub_action_description

                description = _sub_action_description("", name)
                from core.llm.tools.schemas import (
                    action_input_schema,
                    react_input_schema,
                )

                input_schema = (
                    action_input_schema(name)
                    if use_full_input_schema
                    else react_input_schema(name)
                )
                output_schema = {}
                tool_kind = (kind_override or {}).get(name, "function")
                agent_name = ""
            if name == "finish":
                from core.llm.tools.schemas import react_input_schema

                input_schema = react_input_schema(name)
            tools.append(
                ToolDefinition(
                    name=name,
                    description=description,
                    input_schema=input_schema,
                    output_schema=output_schema,
                    kind=tool_kind if tool_kind in ("function", "agent") else "function",
                    agent_name=agent_name,
                )
            )
        return tools

    def pipeline_actions(self, agent: str) -> list[str]:
        return [
            s.name
            for s in self.list_tools(agent)
            if s.kind == ToolKind.WRITE_PIPELINE
        ]

    def ad_hoc_actions(self, agent: str) -> list[str]:
        return [
            s.name for s in self.list_tools(agent) if s.kind == ToolKind.WRITE_AD_HOC
        ]

    def read_actions(self, agent: str) -> list[str]:
        return [s.name for s in self.list_tools(agent) if s.kind == ToolKind.READ]

    def available_actions(self, agent: str) -> list[str]:
        return [
            s.name
            for s in self.list_tools(agent)
            if s.kind != ToolKind.AGENT_DELEGATE
        ]


_REGISTRY: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        import time

        from core.llm.tools.bootstrap import register_all_tools
        from core.extensions.tool_loader import load_extension_tools
        from core.logging.perf import log_perf

        start = time.perf_counter()
        _REGISTRY = ToolRegistry()
        register_all_tools(_REGISTRY)
        load_extension_tools(_REGISTRY)
        log_perf(
            "startup",
            "tool_registry 构建完成",
            duration_ms=(time.perf_counter() - start) * 1000,
            tool_count=len(_REGISTRY.list_tools()),
        )
    return _REGISTRY


def reset_tool_registry() -> None:
    """清空 Registry 单例（测试用）。"""
    global _REGISTRY
    _REGISTRY = None
    from core.llm.tools.shared import agent_tools

    agent_tools._AGENT_TOOLS_CACHE = None
