"""通用 ReAct 运行时：Thought → Action → Observation，支持主/子 Agent 复用。"""

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from core.conversation import ConversationRole, ConversationStore
from core.agents.script_assets import SCRIPT_MUTATION_ACTIONS
from core.constants import MAX_REACT_ITERATIONS, VIDEO_GEN_COST_PER_SHOT_USD
from core.events.emitter import EventEmitter
from core.logging.setup import get_logger, log_stage
from core.models.entities import StepOutput

logger = get_logger("core.agents.react")


@dataclass
class ReActDecision:
    """单轮 ReAct 推理结果。"""

    thought: str
    action: str
    action_input: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRunContext:
    """子 Agent 单次调用的 ReAct 上下文（不含用户原始对话）。"""

    task_brief: str
    work_context: dict[str, Any]
    script_id: str
    step_id: str
    agent_name: str
    completed_actions: set[str] = field(default_factory=set)
    observations: list[str] = field(default_factory=list)
    llm_observations: list[str] = field(default_factory=list)
    history_summary: str = ""
    outputs: list[StepOutput] = field(default_factory=list)
    iteration: int = 0


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
        self._conversations.clear_agent_session(script_id, agent_name)
        self._conversations.add(
            script_id, "agent", ConversationRole.TASK, task_brief, agent_name
        )

        ctx = AgentRunContext(
            task_brief=task_brief,
            work_context=work_context,
            script_id=script_id,
            step_id=step_id,
            agent_name=agent_name,
        )

        log_stage(logger, "react.agent", "子 Agent ReAct 开始", agent=agent_name, step_id=step_id)

        from core.prompt.context_window import prepare_sub_agent_context

        for _ in range(MAX_REACT_ITERATIONS):
            ctx.iteration += 1
            prepared = prepare_sub_agent_context(ctx, self._conversations)
            ctx.llm_observations = prepared.observations
            ctx.history_summary = prepared.history_summary
            decision = await decide(ctx)

            self._conversations.add(
                script_id, "agent", ConversationRole.THOUGHT, decision.thought, agent_name
            )
            await self._emit_agent_react(
                script_id, agent_name, display_name, step_id, "agent_react_thought",
                {"iteration": ctx.iteration, "thought": decision.thought},
            )

            if decision.action == "finish":
                await self._emit_agent_react(
                    script_id, agent_name, display_name, step_id, "agent_react_action",
                    {"iteration": ctx.iteration, "action": "finish"},
                )
                break

            self._conversations.add(
                script_id,
                "agent",
                ConversationRole.ACTION,
                f"{decision.action}: {decision.action_input}",
                agent_name,
            )
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
            )

            observation = await act(decision.action, ctx)
            ctx.observations.append(observation)
            ctx.completed_actions.add(decision.action)

            self._conversations.add(
                script_id, "agent", ConversationRole.OBSERVATION, observation, agent_name
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
                },
            )

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
        await self._emit_agent_react(
            script_id,
            agent_name,
            display_name,
            step_id,
            "agent_react_finished",
            {"iterations": ctx.iteration, "output_count": len(ctx.outputs)},
        )
        return ctx.outputs

    async def _emit_agent_react(
        self,
        script_id: str,
        agent_name: str,
        display_name: str,
        step_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        await self._emitter.emit(
            {
                "type": event_type,
                "script_id": script_id,
                "agent_name": agent_name,
                "agent_display_name": display_name,
                "step_id": step_id,
                **payload,
            }
        )
