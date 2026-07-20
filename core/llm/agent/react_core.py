"""通用 ReAct 运行时：Thought → Action → Observation，支持主/子 Agent 复用。"""

import asyncio
import time
from dataclasses import dataclass, field, replace
from typing import Any, Awaitable, Callable

from core.conversation import ConversationStore
from core.execution.cancel import ExecutionCancelledError, check_cancelled, wait_or_cancel
from core.llm.hook.react_guard import (
    DuplicateActionAbortError,
    EditComposeMissingAssetsError,
    ImageGenerationAbortError,
    ReActLoopGuard,
    TtsAbortError,
)
from core.llm.hook.return_to_master import ReturnToMasterError
from core.llm.agent.script_assets import SCRIPT_MUTATION_ACTIONS
from core.llm.tool_call_batch import BatchExecutionMode, merge_batch_observations
from core.constants import MAX_REACT_ITERATIONS
from core.events.emitter import EventEmitter
from core.logging.perf import log_perf
from core.logging.setup import get_logger, log_stage
from core.llm.model.plan_context import PlanSlice
from core.llm.model.plan_context import extract_plan_update, format_plan_observation
from core.models.entities import StepOutput

logger = get_logger("core.agents.react")


@dataclass
class ToolCallDecision:
    """单条 tool_call 决策（含 LLM 原始 id）。"""

    tool_call_id: str
    action: str
    action_input: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReActDecision:
    """单轮 ReAct 推理结果（可含多个同轮 tool_calls）。"""

    thought: str
    action: str
    action_input: dict[str, Any] = field(default_factory=dict)
    calls: list[ToolCallDecision] = field(default_factory=list)
    batch_mode: BatchExecutionMode = "parallel"

    def __post_init__(self) -> None:
        if self.calls:
            primary = self.calls[0]
            self.action = primary.action
            self.action_input = dict(primary.action_input or {})
        elif self.action:
            self.calls = [
                ToolCallDecision(
                    tool_call_id="",
                    action=self.action,
                    action_input=dict(self.action_input or {}),
                )
            ]

    @property
    def is_batch(self) -> bool:
        """同轮是否包含多个 tool_calls。"""
        return len(self.calls) > 1

@dataclass
class AgentRunContext:
    """子 Agent 单次调用的 ReAct 上下文（不含用户原始对话）。"""

    task_brief: str
    work_context: dict[str, Any]
    script_id: str
    step_id: str
    agent_name: str
    conversation_id: str = ""
    project_id: str = ""
    completed_actions: set[str] = field(default_factory=set)
    observations: list[str] = field(default_factory=list)
    llm_observations: list[str] = field(default_factory=list)
    history_summary: str = ""
    outputs: list[StepOutput] = field(default_factory=list)
    iteration: int = 0
    current_action_input: dict[str, Any] = field(default_factory=dict)
    last_user_values: dict[str, Any] | None = None
    last_tool_structured: dict[str, Any] | None = None
    last_action_ok: bool = True
    plan_slice: PlanSlice | None = None


@dataclass
class MasterRunContext:
    """主 Agent ReAct 上下文（含用户诉求摘要，不传递给子 Agent）。"""

    project_id: str
    script_id: str
    user_message: str
    style_mode: Any
    generation_mode: Any
    conversation_id: str = ""
    completed_step_types: set[str] = field(default_factory=set)
    observations: list[str] = field(default_factory=list)
    iteration: int = 0


DecideFn = Callable[[AgentRunContext], Awaitable[ReActDecision]]
ActFn = Callable[[str, AgentRunContext], Awaitable[str]]


class ReActRunner:
    """通用 ReAct 循环执行器。"""

    def __init__(
        self,
        emitter: EventEmitter,
        conversations: ConversationStore,
    ) -> None:
        self._emitter = emitter
        self._conversations = conversations

    async def run_agent(
        self,
        agent_name: str,
        display_name: str,
        task_brief: str,
        work_context: dict[str, Any],
        script_id: str,
        step_id: str,
        decide: DecideFn,
        act: ActFn,
    ) -> list[StepOutput]:
        """运行子 Agent ReAct：任务简报进入隔离会话，不接触用户对话。"""
        conversation_id = str(work_context.get("conversation_id", ""))
        project_id = str(work_context.get("project_id", ""))
        if not conversation_id:
            raise ValueError("子 Agent 需要 conversation_id")

        self._conversations.clear_agent_session(conversation_id, agent_name)
        self._conversations.add_task_brief(
            conversation_id,
            project_id,
            script_id,
            task_brief,
            agent_name,
        )

        plan_slice_raw = work_context.get("plan_slice")
        plan_slice: PlanSlice | None = None
        if isinstance(plan_slice_raw, PlanSlice):
            plan_slice = plan_slice_raw
        elif isinstance(plan_slice_raw, dict) and plan_slice_raw:
            plan_slice = PlanSlice.model_validate(plan_slice_raw)

        ctx = AgentRunContext(
            task_brief=task_brief,
            work_context=work_context,
            script_id=script_id,
            step_id=step_id,
            agent_name=agent_name,
            conversation_id=conversation_id,
            project_id=project_id,
            plan_slice=plan_slice,
        )

        log_stage(logger, "react.agent", "子 Agent ReAct 开始", agent=agent_name, step_id=step_id)
        agent_start = time.perf_counter()

        from core.llm.prompt.context_window import prepare_sub_agent_context

        loop_guard = ReActLoopGuard()

        for _ in range(MAX_REACT_ITERATIONS):
            check_cancelled(script_id)
            ctx.iteration += 1
            prepared = prepare_sub_agent_context(ctx, self._conversations)
            ctx.llm_observations = prepared.observations
            ctx.history_summary = prepared.history_summary
            decision = await wait_or_cancel(script_id, decide(ctx))
            plan_update = extract_plan_update(decision.action_input)

            await self._emit_agent_react(
                script_id, agent_name, display_name, step_id, "agent_react_thought",
                {"iteration": ctx.iteration, "thought": decision.thought},
                conversation_id=ctx.conversation_id,
            )

            if decision.action == "finish":
                self._conversations.add_react_turn(
                    ctx.conversation_id,
                    ctx.project_id,
                    script_id,
                    thought=decision.thought,
                    action="finish",
                    action_input=decision.action_input,
                    observation=str(
                        decision.action_input.get("observation", "子 Agent 完成")
                    ),
                    channel="agent",
                    agent_name=agent_name,
                    step_id=step_id,
                )
                await self._emit_agent_react(
                    script_id, agent_name, display_name, step_id, "agent_react_action",
                    {"iteration": ctx.iteration, "action": "finish"},
                    conversation_id=ctx.conversation_id,
                )
                break

            if decision.is_batch:
                await self._run_batch_turn(
                    ctx=ctx,
                    script_id=script_id,
                    agent_name=agent_name,
                    display_name=display_name,
                    step_id=step_id,
                    decision=decision,
                    plan_update=plan_update,
                    act=act,
                    loop_guard=loop_guard,
                )
                continue

            await self._emit_agent_react(
                script_id,
                agent_name,
                display_name,
                step_id,
                "agent_react_action",
                {
                    "iteration": ctx.iteration,
                    "action": decision.action,
                    "action_input": decision.action_input,
                },
                conversation_id=ctx.conversation_id,
            )

            ctx.current_action_input = dict(decision.action_input or {})
            duplicate_obs = loop_guard.record(decision.action, decision.action_input)
            if duplicate_obs:
                ctx.observations.append(duplicate_obs)
                self._conversations.add_react_turn(
                    ctx.conversation_id,
                    ctx.project_id,
                    script_id,
                    thought=decision.thought,
                    action=decision.action,
                    action_input=decision.action_input,
                    observation=duplicate_obs,
                    channel="agent",
                    agent_name=agent_name,
                    step_id=step_id,
                )
                await self._emit_agent_react(
                    script_id,
                    agent_name,
                    display_name,
                    step_id,
                    "agent_react_observation",
                    {
                        "iteration": ctx.iteration,
                        "observation": duplicate_obs,
                        "action": decision.action,
                        "user_values": None,
                    },
                    conversation_id=ctx.conversation_id,
                )
                raise DuplicateActionAbortError(decision.action, duplicate_obs)

            try:
                observation = await wait_or_cancel(script_id, act(decision.action, ctx))
            except ExecutionCancelledError:
                raise
            except ImageGenerationAbortError:
                raise
            except ReturnToMasterError as e:
                self._conversations.clear_agent_session(conversation_id, agent_name)
                self._conversations.suspend_agent_session(
                    conversation_id,
                    agent_name,
                    e.to_dict(),
                )
                raise
            except EditComposeMissingAssetsError as e:
                self._conversations.clear_agent_session(conversation_id, agent_name)
                self._conversations.suspend_agent_session(
                    conversation_id,
                    agent_name,
                    e.to_dict(),
                )
                raise
            except TtsAbortError:
                raise

            if plan_update:
                ctx.observations.append(format_plan_observation(plan_update))
            ctx.observations.append(observation)
            if ctx.last_action_ok is not False:
                ctx.completed_actions.add(decision.action)

            self._conversations.add_react_turn(
                ctx.conversation_id,
                ctx.project_id,
                script_id,
                thought=decision.thought,
                action=decision.action,
                action_input=decision.action_input,
                observation=observation,
                channel="agent",
                agent_name=agent_name,
                step_id=step_id,
            )
            await self._emit_agent_react(
                script_id,
                agent_name,
                display_name,
                step_id,
                "agent_react_observation",
                {
                    "iteration": ctx.iteration,
                    "observation": observation,
                    "action": decision.action,
                    "user_values": ctx.last_user_values,
                    "tool_structured": ctx.last_tool_structured,
                },
                conversation_id=ctx.conversation_id,
            )
            ctx.last_user_values = None
            ctx.last_tool_structured = None

            if agent_name == "script_agent" and decision.action in SCRIPT_MUTATION_ACTIONS:
                await self._emitter.emit(
                    {
                        "type": "assets_changed",
                        "script_id": script_id,
                        "agent_name": agent_name,
                        "action": decision.action,
                        "step_id": step_id,
                    }
                )

        log_stage(
            logger,
            "react.agent",
            "子 Agent ReAct 结束",
            agent=agent_name,
            iterations=ctx.iteration,
            outputs=len(ctx.outputs),
        )
        log_perf(
            "react.agent",
            "子 Agent ReAct 结束",
            duration_ms=(time.perf_counter() - agent_start) * 1000,
            agent=agent_name,
            step_id=step_id,
            iterations=ctx.iteration,
            outputs=len(ctx.outputs),
        )
        await self._emit_agent_react(
            script_id,
            agent_name,
            display_name,
            step_id,
            "agent_react_finished",
            {"iterations": ctx.iteration, "output_count": len(ctx.outputs)},
            conversation_id=ctx.conversation_id,
        )
        return ctx.outputs

    async def _run_batch_turn(
        self,
        *,
        ctx: AgentRunContext,
        script_id: str,
        agent_name: str,
        display_name: str,
        step_id: str,
        decision: ReActDecision,
        plan_update: Any,
        act: ActFn,
        loop_guard: ReActLoopGuard,
    ) -> None:
        """同轮执行多个 tool_calls（白名单并行，否则顺序）。"""
        batch_mode = decision.batch_mode
        batch_actions = [
            {
                "action": call.action,
                "action_input": dict(call.action_input or {}),
                "tool_call_id": call.tool_call_id,
            }
            for call in decision.calls
        ]
        await self._emit_agent_react(
            script_id,
            agent_name,
            display_name,
            step_id,
            "agent_react_action_batch",
            {
                "iteration": ctx.iteration,
                "actions": batch_actions,
                "batch_size": len(decision.calls),
                "batch_mode": batch_mode,
            },
            conversation_id=ctx.conversation_id,
        )

        for call in decision.calls:
            duplicate_obs = loop_guard.record(call.action, call.action_input)
            if duplicate_obs:
                ctx.observations.append(duplicate_obs)
                self._conversations.add_react_turn_batch(
                    ctx.conversation_id,
                    ctx.project_id,
                    script_id,
                    thought=decision.thought,
                    calls=[
                        (
                            c.tool_call_id,
                            c.action,
                            dict(c.action_input or {}),
                            duplicate_obs if c.action == call.action else "未执行（同轮重复检测中止）",
                        )
                        for c in decision.calls
                    ],
                    channel="agent",
                    agent_name=agent_name,
                    step_id=step_id,
                )
                await self._emit_agent_react(
                    script_id,
                    agent_name,
                    display_name,
                    step_id,
                    "agent_react_observation",
                    {
                        "iteration": ctx.iteration,
                        "observation": duplicate_obs,
                        "action": call.action,
                        "batch_size": len(decision.calls),
                        "batch_mode": batch_mode,
                    },
                    conversation_id=ctx.conversation_id,
                )
                raise DuplicateActionAbortError(call.action, duplicate_obs)

        async def _run_one(call: ToolCallDecision) -> tuple[str, str, str | BaseException]:
            """执行单条 tool_call，普通异常作为结果返回。"""
            sub_ctx = replace(ctx, current_action_input=dict(call.action_input or {}))
            try:
                obs = await wait_or_cancel(script_id, act(call.action, sub_ctx))
                return call.action, call.tool_call_id, obs
            except BaseException as e:
                return call.action, call.tool_call_id, e

        if batch_mode == "sequential":
            results: list[tuple[str, str, str | BaseException]] = []
            for call in decision.calls:
                results.append(await _run_one(call))
        else:
            results = await asyncio.gather(*[_run_one(c) for c in decision.calls])

        for item in results:
            action, _tid, outcome = item
            if isinstance(outcome, ReturnToMasterError):
                self._conversations.clear_agent_session(ctx.conversation_id, agent_name)
                self._conversations.suspend_agent_session(
                    ctx.conversation_id,
                    agent_name,
                    outcome.to_dict(),
                )
                raise outcome
            if isinstance(outcome, EditComposeMissingAssetsError):
                self._conversations.clear_agent_session(ctx.conversation_id, agent_name)
                self._conversations.suspend_agent_session(
                    ctx.conversation_id,
                    agent_name,
                    outcome.to_dict(),
                )
                raise outcome
            if isinstance(outcome, (ExecutionCancelledError, ImageGenerationAbortError, TtsAbortError)):
                raise outcome

        observation = merge_batch_observations(results)
        if plan_update:
            ctx.observations.append(format_plan_observation(plan_update))
        ctx.observations.append(observation)

        for call in decision.calls:
            if ctx.last_action_ok is not False:
                ctx.completed_actions.add(call.action)

        persist_calls = []
        for call, (_action, _tid, outcome) in zip(decision.calls, results, strict=True):
            if isinstance(outcome, BaseException):
                obs_text = f"失败：{outcome}"
            else:
                obs_text = str(outcome)
            persist_calls.append(
                (call.tool_call_id, call.action, dict(call.action_input or {}), obs_text)
            )

        self._conversations.add_react_turn_batch(
            ctx.conversation_id,
            ctx.project_id,
            script_id,
            thought=decision.thought,
            calls=persist_calls,
            channel="agent",
            agent_name=agent_name,
            step_id=step_id,
        )

        await self._emit_agent_react(
            script_id,
            agent_name,
            display_name,
            step_id,
            "agent_react_observation",
            {
                "iteration": ctx.iteration,
                "observation": observation,
                "actions": batch_actions,
                "batch_size": len(decision.calls),
                "batch_mode": batch_mode,
            },
            conversation_id=ctx.conversation_id,
        )

        if agent_name == "script_agent":
            for call in decision.calls:
                if call.action in SCRIPT_MUTATION_ACTIONS:
                    await self._emitter.emit(
                        {
                            "type": "assets_changed",
                            "script_id": script_id,
                            "agent_name": agent_name,
                            "action": call.action,
                            "step_id": step_id,
                        }
                    )

    async def _emit_agent_react(
        self,
        script_id: str,
        agent_name: str,
        display_name: str,
        step_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        conversation_id: str = "",
    ) -> None:
        await self._emitter.emit(
            {
                "type": event_type,
                "script_id": script_id,
                "agent_name": agent_name,
                "agent_display_name": display_name,
                "step_id": step_id,
                "conversation_id": conversation_id,
                **payload,
            }
        )
