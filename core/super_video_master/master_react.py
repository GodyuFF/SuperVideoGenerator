"""超级视频大师 ReAct 编排：与用户对话隔离，向子 Agent 下发任务简报。"""

import asyncio
from typing import Any

from core.a2ui.manager import ConfirmationManager, ConfirmationRejectedError
from core.agents.conversation import ConversationRole, ConversationStore
from core.agents.registry import AgentRegistry
from core.super_video_master import MASTER_AGENT_NAME
from core.super_video_master.actions import (
    ACTION_TO_STEP,
    STEP_META,
    TASK_BRIEFS,
    action_kind,
    action_label,
)
from core.agents.react_core import MasterRunContext, ReActDecision
from core.constants import MAX_REACT_ITERATIONS, VIDEO_GEN_COST_PER_SHOT_USD
from core.events.emitter import EventEmitter
from core.llm.react_decider import LLMReActDecider
from core.llm.react_session import create_master_react_session, ReActSession
from core.logging.setup import get_logger, log_stage
from core.models.entities import (
    GenerationMode,
    PlanDocument,
    PlanStep,
    ScriptStatus,
    StepStatus,
    VideoStyleMode,
)
from core.store.memory import MemoryStore
from core.tools.master_tools import MasterToolExecutor
from core.llm.streaming import OnDelta, ReactXmlThoughtParser
logger = get_logger("core.super_video_master.react")


class MasterReActPolicy:
    """主 Agent ReAct 策略：基于 ReActSession（tools + sub_agents）做 LLM XML 决策。"""

    def __init__(self, llm_decider: LLMReActDecider) -> None:
        self._llm_decider = llm_decider

    async def decide(
        self,
        session: ReActSession,
        on_delta: OnDelta | None = None,
    ) -> ReActDecision:
        return await self._llm_decider.decide_session(session, on_delta=on_delta)


class MasterReActEngine:
    """主 Agent ReAct：仅主会话可见用户消息，子 Agent 仅接收任务简报。"""

    def __init__(
        self,
        store: MemoryStore,
        emitter: EventEmitter,
        registry: AgentRegistry,
        conversations: ConversationStore,
        confirmation: ConfirmationManager,
        llm_decider: LLMReActDecider,
    ) -> None:
        self._store = store
        self._emitter = emitter
        self._registry = registry
        self._conversations = conversations
        self._confirmation = confirmation
        self._policy = MasterReActPolicy(llm_decider)
        self._tool_executor = MasterToolExecutor(store)

    async def _emit(self, script_id: str, event_type: str, payload: dict[str, Any]) -> None:
        await self._emitter.emit({"script_id": script_id, "type": event_type, **payload})

    def _react_action_payload(
        self,
        decision: ReActDecision,
        conversation_id: str,
        iteration: int,
        *,
        step_type: str | None = None,
        step_id: str | None = None,
    ) -> dict[str, Any]:
        """构造 react_action 事件 payload，保留 LLM action_input 并附中文标签。"""
        llm_input = dict(decision.action_input)
        payload: dict[str, Any] = {
            "iteration": iteration,
            "action": decision.action,
            "action_label": action_label(decision.action),
            "action_kind": action_kind(decision.action),
            "llm_action_input": llm_input,
            "action_input": llm_input,
            "conversation_id": conversation_id,
        }
        if step_type is not None:
            payload["step_type"] = step_type
        if step_id is not None:
            payload["step_id"] = step_id
        return payload

    def _make_thought_stream_handler(
        self,
        script_id: str,
        conversation_id: str,
        stream_id: str,
        iteration: int,
    ) -> OnDelta:
        parser = ReactXmlThoughtParser()

        async def on_delta(raw_delta: str) -> None:
            thought_delta = parser.feed(raw_delta)
            if not thought_delta:
                return
            await self._emit(
                script_id,
                "llm_stream_delta",
                {
                    "stream_id": stream_id,
                    "delta": thought_delta,
                    "kind": "react_thought",
                    "visibility": "user",
                    "conversation_id": conversation_id,
                    "iteration": iteration,
                },
            )

        return on_delta

    async def _start_llm_stream(
        self,
        script_id: str,
        conversation_id: str,
        stream_id: str,
        kind: str,
        **extra: Any,
    ) -> None:
        await self._emit(
            script_id,
            "llm_stream_start",
            {
                "stream_id": stream_id,
                "kind": kind,
                "conversation_id": conversation_id,
                **extra,
            },
        )

    async def _end_llm_stream(
        self,
        script_id: str,
        conversation_id: str,
        stream_id: str,
        kind: str,
        **extra: Any,
    ) -> None:
        await self._emit(
            script_id,
            "llm_stream_end",
            {
                "stream_id": stream_id,
                "kind": kind,
                "conversation_id": conversation_id,
                **extra,
            },
        )

    def _build_delegate_task_brief(
        self,
        ctx: MasterRunContext,
        step_type: str,
        decision: ReActDecision,
    ) -> str:
        parts = [TASK_BRIEFS[step_type], f"用户创意：{ctx.user_message}"]
        note = decision.action_input.get("备注")
        if note:
            parts.append(f"主编排说明：{note}")
        script = self._store.get_script(ctx.script_id)
        if script and step_type == "script_design":
            parts.append(f"目标时长 {script.duration_sec}s")
        return " ".join(parts)

    def _make_step(self, step_type: str, depends_on: list[str]) -> PlanStep:
        meta = STEP_META[step_type]
        estimated_cost: float | None = None
        if step_type == "video_gen":
            estimated_cost = VIDEO_GEN_COST_PER_SHOT_USD * 3
        return PlanStep(
            type=step_type,
            title=meta["title"],
            description=meta["description"],
            agent=meta["agent"],
            depends_on=depends_on,
            estimated_cost_usd=estimated_cost,
        )

    async def _video_cost_gate(
        self,
        script_id: str,
        step: PlanStep,
        generation_mode: GenerationMode,
    ) -> bool:
        vp = self._store.get_video_plan_for_script(script_id)
        shot_count = len(vp.shots) if vp else 3
        cost = step.estimated_cost_usd or (VIDEO_GEN_COST_PER_SHOT_USD * shot_count)
        step.status = StepStatus.AWAITING_CONFIRMATION
        await self._emit(
            script_id,
            "step_awaiting_confirmation",
            {
                "step_id": step.id,
                "step_type": step.type,
                "estimated_cost_usd": cost,
            },
        )
        try:
            await self._confirmation.wait_for_video_gen(
                step_id=step.id,
                shot_count=shot_count,
                estimated_cost_usd=cost,
                mode=generation_mode.value,
            )
            return True
        except ConfirmationRejectedError:
            step.status = StepStatus.FAILED
            step.error = "用户拒绝视频生成费用"
            await self._emit(
                script_id,
                "step_failed",
                {"step_id": step.id, "error": step.error},
            )
            return False

    async def run(
        self,
        project_id: str,
        script_id: str,
        user_message: str,
        style_mode: VideoStyleMode,
        generation_mode: GenerationMode,
        conversation_id: str,
    ) -> list[str]:
        script = self._store.get_script(script_id)
        if not script:
            raise ValueError("剧本不存在")

        ctx = MasterRunContext(
            project_id=project_id,
            script_id=script_id,
            user_message=user_message,
            style_mode=style_mode,
            generation_mode=generation_mode,
            conversation_id=conversation_id,
        )

        session = create_master_react_session(
            conversation_id=conversation_id,
            project_id=project_id,
            script_id=script_id,
            user_message=user_message,
            style_mode=style_mode,
            generation_mode=generation_mode,
        )

        plan = PlanDocument(
            version=script.plan_version + 1,
            goal=script.title,
            constraints={
                "duration_sec": script.duration_sec,
                "style_mode": style_mode.value,
                "orchestration": "react",
                "conversation_isolation": True,
            },
            steps=[],
        )
        self._store.set_plan(script_id, plan)
        script.plan_version = plan.version
        script.status = ScriptStatus.EXECUTING

        log_stage(logger, "master.react", "主 Agent ReAct 开始", script_id=script_id)
        await self._emit(
            script_id,
            "conversation_started",
            {
                "conversation_id": conversation_id,
                "agent_name": MASTER_AGENT_NAME,
            },
        )
        await self._emit(script_id, "react_started", {"message": user_message, "conversation_id": conversation_id})

        execution_started = False
        last_step_id: str | None = None

        try:
            for _ in range(MAX_REACT_ITERATIONS):
                ctx.iteration += 1
                session.iteration = ctx.iteration
                session.observations = list(ctx.observations)
                session.completed_step_types = set(ctx.completed_step_types)

                stream_id = f"master-thought-{ctx.iteration}"
                await self._start_llm_stream(
                    script_id,
                    conversation_id,
                    stream_id,
                    "react_thought",
                    iteration=ctx.iteration,
                    visibility="user",
                )
                on_delta = self._make_thought_stream_handler(
                    script_id,
                    conversation_id,
                    stream_id,
                    ctx.iteration,
                )

                try:
                    decision = await self._policy.decide(session, on_delta=on_delta)
                except (RuntimeError, ValueError) as e:
                    observation = f"主编排决策失败：{e}"
                    ctx.observations.append(observation)
                    session.observations = list(ctx.observations)
                    await self._emit(
                        script_id,
                        "react_observation",
                        {
                            "iteration": ctx.iteration,
                            "observation": observation,
                            "conversation_id": conversation_id,
                            "kind": "master",
                        },
                    )
                    await self._end_llm_stream(
                        script_id,
                        conversation_id,
                        stream_id,
                        "react_thought",
                        iteration=ctx.iteration,
                        visibility="user",
                    )
                    continue

                await self._end_llm_stream(
                    script_id,
                    conversation_id,
                    stream_id,
                    "react_thought",
                    iteration=ctx.iteration,
                    visibility="user",
                )

                if session.is_delegate_action(decision.action):
                    step_type = session.step_type_for_delegate(decision.action)
                    if step_type and step_type in ctx.completed_step_types:
                        ctx.observations.append(
                            f"步骤 {step_type} 已完成，请勿重复委派 {decision.action}。"
                        )
                        session.observations = list(ctx.observations)
                        continue

                if decision.action == "finish":
                    await self._emit(
                        script_id,
                        "react_action",
                        self._react_action_payload(
                            decision, conversation_id, ctx.iteration
                        ),
                    )
                    break

                if session.is_tool_action(decision.action):
                    await self._emit(
                        script_id,
                        "react_action",
                        self._react_action_payload(
                            decision, conversation_id, ctx.iteration
                        ),
                    )
                    try:
                        observation = await self._tool_executor.execute(
                            decision.action, script_id
                        )
                    except Exception as e:
                        observation = f"工具 {decision.action} 执行失败：{e}"
                    session.completed_tools.add(decision.action.removeprefix("tool_"))
                    ctx.observations.append(observation)
                    self._conversations.add(
                        script_id, "master", ConversationRole.OBSERVATION, observation, "super_video_master"
                    )
                    await self._emit(
                        script_id,
                        "react_observation",
                        {
                            "iteration": ctx.iteration,
                            "observation": observation,
                            "conversation_id": conversation_id,
                            "kind": "tool",
                        },
                    )
                    continue

                if not session.is_delegate_action(decision.action):
                    observation = f"未知行动「{decision.action}」，已跳过。"
                    ctx.observations.append(observation)
                    await self._emit(
                        script_id,
                        "react_observation",
                        {
                            "iteration": ctx.iteration,
                            "observation": observation,
                            "conversation_id": conversation_id,
                        },
                    )
                    continue

                step_type = ACTION_TO_STEP[decision.action]
                depends_on = [last_step_id] if last_step_id else []
                step = self._make_step(step_type, depends_on)
                plan.steps.append(step)
                self._store.set_plan(script_id, plan)
                last_step_id = step.id

                await self._emit(
                    script_id,
                    "react_action",
                    self._react_action_payload(
                        decision,
                        conversation_id,
                        ctx.iteration,
                        step_type=step_type,
                        step_id=step.id,
                    ),
                )
                await self._emit(script_id, "plan_ready", {"plan": plan.model_dump()})

                if not execution_started:
                    await self._emit(script_id, "execution_started", {})
                    execution_started = True

                if step_type == "video_gen":
                    ok = await self._video_cost_gate(script_id, step, generation_mode)
                    if not ok:
                        observation = f"步骤「{step.title}」因费用确认被拒绝。"
                        ctx.observations.append(observation)
                        await self._emit(
                            script_id,
                            "react_observation",
                            {
                                "iteration": ctx.iteration,
                                "observation": observation,
                                "step_id": step.id,
                                "step_status": step.status.value,
                            },
                        )
                        break

                step.status = StepStatus.RUNNING
                await self._emit(
                    script_id,
                    "step_started",
                    {"step_id": step.id, "step_type": step.type},
                )

                task_brief = self._build_delegate_task_brief(ctx, step_type, decision)

                agent = self._registry.get(step.agent)
                work_context = {
                    "project_id": project_id,
                    "script_id": script_id,
                    "style_mode": style_mode,
                    "generation_mode": generation_mode,
                    "conversation_id": conversation_id,
                    "user_message": ctx.user_message,
                }

                try:
                    sub_task = asyncio.create_task(
                        agent.run(
                            task_brief=task_brief,
                            work_context=work_context,
                            script_id=script_id,
                            step_id=step.id,
                        )
                    )
                    outputs = await sub_task
                    step.outputs = outputs
                    step.status = StepStatus.COMPLETED
                    step.progress = 100
                    await self._emit(
                        script_id,
                        "step_completed",
                        {
                            "step_id": step.id,
                            "outputs": [o.model_dump() for o in outputs],
                        },
                    )
                except Exception as e:
                    step.status = StepStatus.FAILED
                    step.error = str(e)
                    await self._emit(
                        script_id,
                        "step_failed",
                        {"step_id": step.id, "error": str(e)},
                    )

                labels = [o.label for o in step.outputs[:3]]
                if step.status == StepStatus.COMPLETED:
                    suffix = f"，产出：{', '.join(labels)}" if labels else ""
                    observation = f"已委派 {agent.display_name}，步骤「{step.title}」完成{suffix}。"
                    ctx.completed_step_types.add(step_type)
                else:
                    observation = (
                        f"委派 {agent.display_name} 失败：{step.error or '未知错误'}。"
                    )

                ctx.observations.append(observation)
                await self._emit(
                    script_id,
                    "react_observation",
                    {
                        "iteration": ctx.iteration,
                        "observation": observation,
                        "step_id": step.id,
                        "step_status": step.status.value,
                        "conversation_id": conversation_id,
                        "kind": "sub_agent",
                    },
                )

                if step.status == StepStatus.FAILED:
                    break

            await self._finalize(script_id, plan)

            await self._emit(
                script_id,
                "react_finished",
                {
                    "iterations": ctx.iteration,
                    "status": script.status.value,
                    "completed_steps": list(ctx.completed_step_types),
                    "conversation_id": conversation_id,
                },
            )
            log_stage(
                logger,
                "master.react",
                "主 Agent ReAct 结束",
                script_id=script_id,
                iterations=ctx.iteration,
                status=script.status.value,
            )
            return list(ctx.observations)
        except Exception as e:
            script = self._store.get_script(script_id)
            if script and script.status == ScriptStatus.EXECUTING:
                script.status = ScriptStatus.FAILED
            await self._emit(
                script_id,
                "execution_failed",
                {"script_id": script_id, "error": str(e)},
            )
            raise

    async def _finalize(self, script_id: str, plan: PlanDocument) -> None:
        script = self._store.get_script(script_id)
        if not script:
            return

        if plan.steps and all(
            s.status.value in ("completed", "skipped") for s in plan.steps
        ):
            script.status = ScriptStatus.COMPLETED
            final_url = ""
            for step in plan.steps:
                if step.type == "edit_compose" and step.outputs:
                    final_url = step.outputs[0].url
            await self._emitter.emit(
                {
                    "type": "project_completed",
                    "script_id": script_id,
                    "output_url": final_url,
                }
            )
            return

        if any(s.status == StepStatus.FAILED for s in plan.steps):
            script.status = ScriptStatus.FAILED
            await self._emitter.emit({"type": "execution_failed", "script_id": script_id})
            return

        if script.status == ScriptStatus.EXECUTING:
            script.status = ScriptStatus.COMPLETED
