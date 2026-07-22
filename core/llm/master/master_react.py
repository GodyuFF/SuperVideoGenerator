"""超级视频大师 ReAct 编排：与用户对话隔离，向子 Agent 下发任务简报。"""

import asyncio
import time
from typing import Any

from core.llm.a2ui.manager import ConfirmationManager
from core.llm.a2ui.schemas import A2UIComponent
from core.llm.hook.return_to_master import ReturnToMasterError
from core.llm.hook.react_guard import (
    DuplicateActionAbortError,
    EditComposeMissingAssetsError,
    ImageGenerationAbortError,
    TtsAbortError,
)
from core.llm.master.edit_failure import (
    format_edit_compose_failure_observation,
    upstream_steps_to_redo,
)
from core.llm.tools.image.errors import (
    build_image_gen_failure_analysis,
    enrich_failure_names,
    format_image_gen_failure_observation,
)
from core.llm.agent.react_core import MasterRunContext, ReActDecision, ToolCallDecision
from core.llm.agent.registry import AgentRegistry
from core.constants import MAX_REACT_ITERATIONS
from core.conversation import ConversationIndex, ConversationStore
from core.execution.cancel import ExecutionCancelledError, check_cancelled, wait_or_cancel
from core.events.emitter import EventEmitter
from core.llm.client import LLMClient
from core.llm.tools.shared.agent_tools import ASK_USER_QUESTION_ACTION
from core.llm.master.actions import (
    STEP_META,
    TASK_BRIEFS,
    action_kind,
    action_label,
    task_brief_for_step,
    uses_image_text_pipeline,
)
from core.llm.agent.agent_registry import resolve_step_for_roster_agent
from core.llm.master.delegate_tool import DELEGATE_AGENT_ACTION
from core.llm.image_text_config import (
    effective_image_source,
    resolve_image_text_config,
    should_prompt_image_source,
)
from core.llm.hook.confirm_gates import (
    CONFIRM_AFTER_STEP,
    CONFIRM_BEFORE_ACTION,
    build_script_structure_summary,
)
from core.guards.script_style import normalize_style_mode_id
from core.llm.master.session import create_master_react_session
from core.llm.master.tools import MasterToolExecutor
from core.llm.client.stream_delta_batcher import make_batched_delta_handler
from core.llm.react_decide import decide_master_session
from core.llm.model.plan_context import (
    apply_plan_update_to_document,
    build_plan_slice_for_step,
    build_plan_snapshot,
    extract_plan_update,
    normalize_remaining_plan,
    trim_plan_status_history,
)
from core.llm.client.settings import LLMConfigManager
from core.llm.streaming import OnDelta
from core.logging.perf import log_perf
from core.logging.setup import get_logger, log_stage
from core.llm.execution_mode import resolve_execution_mode
from core.models.entities import (
    ExecutionMode,
    GenerationMode,
    ImageSourceMode,
    PlanDocument,
    PlanStep,
    ScriptStatus,
    StepStatus,
    VideoStyleMode,
)
from core.llm.tool_call_batch import ExclusiveToolBatchError, merge_batch_observations
from core.store.memory import MemoryStore
from core.super_video_master import MASTER_AGENT_NAME

logger = get_logger("core.llm.master.react")


class MasterReActEngine:
    """主 Agent ReAct：仅主会话可见用户消息，子 Agent 仅接收任务简报。"""

    def __init__(
        self,
        store: MemoryStore,
        emitter: EventEmitter,
        registry: AgentRegistry,
        conversations: ConversationStore,
        confirmation: ConfirmationManager,
        llm_config: LLMConfigManager,
        llm_client: LLMClient,
        conversation_index: ConversationIndex | None = None,
    ) -> None:
        """初始化主编排 ReAct 引擎。"""
        self._store = store
        self._emitter = emitter
        self._registry = registry
        self._conversations = conversations
        self._confirmation = confirmation
        self._llm_config = llm_config
        self._llm_client = llm_client
        self._conversation_index = conversation_index or ConversationIndex()
        self._tool_executor = MasterToolExecutor(
            store,
            self._conversation_index,
        )
        self._stream_delta_drains: dict[str, Any] = {}

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

    def _persist_master_react_turn(
        self,
        conversation_id: str,
        project_id: str,
        script_id: str,
        decision: ReActDecision,
        observation: str,
    ) -> None:
        """写入主编排单 tool ReAct 轮次。"""
        self._conversations.add_react_turn(
            conversation_id,
            project_id,
            script_id,
            thought=decision.thought,
            action=decision.action,
            action_input=dict(decision.action_input or {}),
            observation=observation,
            channel="master",
        )

    def _persist_master_react_turn_batch(
        self,
        conversation_id: str,
        project_id: str,
        script_id: str,
        decision: ReActDecision,
        results: list[tuple[str, str, str | BaseException]],
    ) -> str:
        """落盘主编排同轮多 tool，并返回合并 observation。"""
        observation = merge_batch_observations(results)
        calls = []
        for call, (_action, _tid, outcome) in zip(decision.calls, results, strict=True):
            if isinstance(outcome, BaseException):
                obs_text = f"失败：{outcome}"
            else:
                obs_text = str(outcome)
            calls.append(
                (call.tool_call_id, call.action, dict(call.action_input or {}), obs_text)
            )
        self._conversations.add_react_turn_batch(
            conversation_id,
            project_id,
            script_id,
            thought=decision.thought,
            calls=calls,
            channel="master",
        )
        return observation

    def _apply_master_plan_update(
        self,
        session: Any,
        plan: PlanDocument,
        script_id: str,
        decision: ReActDecision,
    ) -> str | None:
        """仅在 update_plan / replan 时回写 session 与 PlanDocument。"""
        if decision.action not in ("update_plan", "replan"):
            return None
        update = extract_plan_update(decision.action_input)
        if update is None:
            return "提示：update_plan / replan 须填写 plan_status 与 remaining_plan。"
        session.plan_status_history = trim_plan_status_history(
            [*session.plan_status_history, update.plan_status]
        )
        session.last_remaining_plan = normalize_remaining_plan(update.remaining_plan)
        apply_plan_update_to_document(plan, update)
        self._store.set_plan(script_id, plan)
        session.execution_plan = build_plan_snapshot(plan)
        return None

    async def _emit_plan_updated(
        self,
        script_id: str,
        conversation_id: str,
        plan: PlanDocument,
        session: Any,
        *,
        include_full_plan: bool = False,
        affected_step_ids: list[str] | None = None,
        reason: str | None = None,
    ) -> None:
        """推送 plan 元数据更新；默认轻量 delta，全量 plan 由 plan_ready / replan 承担。"""
        payload: dict[str, Any] = {
            "conversation_id": conversation_id,
            "runtime_summary": plan.runtime_summary,
            "plan_status_history": session.plan_status_history,
            "last_remaining_plan": session.last_remaining_plan,
            "version": plan.version,
        }
        if include_full_plan:
            payload["plan"] = plan.model_dump()
        if affected_step_ids is not None:
            payload["affected_step_ids"] = list(affected_step_ids)
        if reason:
            payload["reason"] = reason
        await self._emit(script_id, "plan_updated", payload)

    def _make_thought_stream_handler(
        self,
        script_id: str,
        conversation_id: str,
        stream_id: str,
        iteration: int,
    ) -> OnDelta:
        async def emit_delta(raw_delta: str) -> None:
            await self._emit(
                script_id,
                "llm_stream_delta",
                {
                    "stream_id": stream_id,
                    "delta": raw_delta,
                    "kind": "react_thought",
                    "visibility": "user",
                    "conversation_id": conversation_id,
                    "iteration": iteration,
                },
            )

        on_delta, drain = make_batched_delta_handler(emit_delta)
        self._stream_delta_drains[stream_id] = drain
        return on_delta

    async def _drain_stream_delta(self, stream_id: str) -> None:
        """刷出流式 delta 批量缓冲。"""
        drain = self._stream_delta_drains.pop(stream_id, None)
        if drain is not None:
            await drain()

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
        session: Any,
        step_type: str,
        decision: ReActDecision,
        *,
        resume_context: dict[str, Any] | None = None,
    ) -> str:
        brief = (session.task_brief or "").strip()
        step_brief = task_brief_for_step(step_type, ctx.style_mode)
        if brief and "用户补充" in brief:
            parts = [step_brief, brief]
        else:
            parts = [step_brief, f"用户创意：{ctx.user_message}"]
            if brief:
                parts.append(brief)
        note = decision.action_input.get("备注")
        if note:
            parts.append(f"主编排说明：{note}")
        if resume_context:
            hint = str(resume_context.get("resume_hint") or resume_context.get("message") or "").strip()
            if hint:
                parts.append(f"续跑上下文：{hint}")
        script = self._store.get_script(ctx.script_id)
        if script and step_type == "script_design":
            parts.append(f"目标时长 {script.duration_sec}s")
        return " ".join(parts)

    def _make_step(self, step_type: str, depends_on: list[str], *, profile_id: str) -> PlanStep:
        """创建计划步骤，Agent 目标按 Profile roster 解析。"""
        from core.llm.agent.agent_registry import resolve_roster_agent_for_step

        meta = STEP_META[step_type]
        agent_id = resolve_roster_agent_for_step(step_type, profile_id) or meta["agent"]
        return PlanStep(
            type=step_type,
            title=meta["title"],
            description=meta["description"],
            agent=agent_id,
            depends_on=depends_on,
        )

    async def run(
        self,
        project_id: str,
        script_id: str,
        user_message: str,
        style_mode: VideoStyleMode,
        generation_mode: GenerationMode,
        conversation_id: str,
        execution_mode: ExecutionMode | None = None,
        skill_overlay: dict[str, Any] | None = None,
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

        project = self._store.get_project(project_id)
        resolved_execution = resolve_execution_mode(project, override=execution_mode)
        goal_mode = resolved_execution == ExecutionMode.GOAL

        session = create_master_react_session(
            conversation_id=conversation_id,
            project_id=project_id,
            script_id=script_id,
            user_message=user_message,
            style_mode=style_mode,
            generation_mode=generation_mode,
            execution_mode=resolved_execution,
        )
        script_for_hints = self._store.get_script(script_id)
        if script_for_hints is not None and script_for_hints.style_hints:
            from core.guards.script_style import format_style_hints_line

            hints_line = format_style_hints_line(script_for_hints.style_hints)
            if hints_line:
                session.extra["style_hints"] = hints_line
        if skill_overlay:
            session.extra["skill_overlay"] = skill_overlay
            mcp_servers = skill_overlay.get("mcp_servers") or []
            if mcp_servers:
                from core.extensions.mcp.loader import ensure_mcp_servers

                await ensure_mcp_servers(list(mcp_servers))

        from core.llm.master.delegate_deps import resolve_delegate_readiness
        from core.llm.master.pipeline_progress import (
            build_pipeline_progress,
            build_resume_observation,
            detect_resume_target_step,
            seed_completed_steps_for_message,
        )
        from core.llm.master.reopen_intent import resolve_reopen_intent

        progress = build_pipeline_progress(self._store, script_id, style_mode)
        reopen_intent = await resolve_reopen_intent(
            user_message,
            progress,
            style_mode,
            llm_client=self._llm_client,
        )
        resume_target = detect_resume_target_step(user_message)
        if reopen_intent.resume_target:
            resume_target = reopen_intent.resume_target
        seeded = seed_completed_steps_for_message(
            self._store,
            script_id,
            style_mode,
            user_message,
            intent=reopen_intent,
        )
        ctx.completed_step_types = set(seeded)
        session.completed_step_types = set(seeded)
        session.extra["pipeline_progress"] = progress
        session.extra["reopen_intent"] = reopen_intent.to_dict()
        session.extra["delegate_readiness"] = resolve_delegate_readiness(
            self._store,
            script_id,
            style_mode,
            profile_id=session._profile_id(),
        )
        if resume_target:
            session.extra["user_resume_target"] = resume_target
        resume_obs = build_resume_observation(
            resume_target=resume_target,
            progress=progress,
            user_message=user_message,
        )
        if resume_obs:
            ctx.observations.append(resume_obs)
            session.observations = list(ctx.observations)
        if reopen_intent.reopen_steps or reopen_intent.full_redo:
            reason = reopen_intent.reason or "用户意图重开"
            steps_txt = (
                "全部步骤"
                if reopen_intent.full_redo
                else "、".join(reopen_intent.reopen_steps)
            )
            ctx.observations.append(
                f"已按意图重开（source={reopen_intent.source}）：{steps_txt}。"
                f"{reason}"
            )
            session.observations = list(ctx.observations)
        if seeded:
            ctx.observations.append(
                "已根据 Store 复用完成步骤："
                + "、".join(sorted(seeded))
                + "。勿无故重跑；用户明确要求重做时除外。"
            )
            session.observations = list(ctx.observations)

        plan_goal = (user_message or "").strip() or script.title
        plan = PlanDocument(
            version=script.plan_version + 1,
            goal=plan_goal,
            constraints={
                "duration_sec": script.duration_sec,
                "style_mode": normalize_style_mode_id(style_mode) or VideoStyleMode.STORYBOOK.value,
                "orchestration": "react",
                "conversation_isolation": True,
            },
            steps=[],
        )
        self._store.set_plan(script_id, plan)
        script.plan_version = plan.version
        script.status = ScriptStatus.EXECUTING

        log_stage(logger, "master.react", "主 Agent ReAct 开始", script_id=script_id)
        react_start = time.perf_counter()
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
        finished_normally = False
        user_aborted = False
        require_script_approval = (
            not goal_mode
            and project is not None
            and project.config.generation.require_script_structure_approval
        ) if project else (not goal_mode)

        try:
            for _ in range(MAX_REACT_ITERATIONS):
                try:
                    check_cancelled(script_id)
                except ExecutionCancelledError:
                    user_aborted = True
                    abort_obs = "用户已中止执行。"
                    ctx.observations.append(abort_obs)
                    session.observations = list(ctx.observations)
                    self._conversations.add_orphan_observation(
                        conversation_id,
                        project_id,
                        script_id,
                        abort_obs,
                        channel="master",
                    )
                    break
                ctx.iteration += 1
                session.iteration = ctx.iteration
                session.observations = list(ctx.observations)
                session.completed_step_types = set(ctx.completed_step_types)
                session.execution_plan = build_plan_snapshot(plan)
                from core.llm.master.delegate_deps import resolve_delegate_readiness

                scan_start = time.perf_counter()
                session.extra["delegate_readiness"] = resolve_delegate_readiness(
                    self._store,
                    script_id,
                    style_mode,
                    profile_id=session._profile_id(),
                )
                session.extra["pipeline_progress"] = build_pipeline_progress(
                    self._store, script_id, style_mode
                )
                scan_ms = (time.perf_counter() - scan_start) * 1000
                log_perf(
                    "master.react",
                    "delegate_scan",
                    duration_ms=scan_ms,
                    iteration=ctx.iteration,
                    script_id=script_id,
                )

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
                    check_cancelled(script_id)
                    decision = await wait_or_cancel(
                        script_id,
                        decide_master_session(
                            self._llm_client,
                            self._llm_config,
                            session,
                            self._conversations,
                            on_delta=on_delta,
                        ),
                    )
                except ExecutionCancelledError:
                    user_aborted = True
                    break
                except ExclusiveToolBatchError as e:
                    # 独占混用属可恢复协议错误：把报错写回 observation，供下一轮纠正
                    observation = f"主编排决策失败：{e}"
                    ctx.observations.append(observation)
                    session.observations = list(ctx.observations)
                    self._conversations.add_orphan_observation(
                        conversation_id,
                        project_id,
                        script_id,
                        observation,
                        channel="master",
                    )
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
                    await self._drain_stream_delta(stream_id)
                    await self._end_llm_stream(
                        script_id,
                        conversation_id,
                        stream_id,
                        "react_thought",
                        iteration=ctx.iteration,
                        visibility="user",
                    )
                    continue
                except (RuntimeError, ValueError) as e:
                    observation = f"主编排决策失败：{e}"
                    ctx.observations.append(observation)
                    session.observations = list(ctx.observations)
                    self._conversations.add_orphan_observation(
                        conversation_id,
                        project_id,
                        script_id,
                        observation,
                        channel="master",
                    )
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
                    await self._drain_stream_delta(stream_id)
                    await self._end_llm_stream(
                        script_id,
                        conversation_id,
                        stream_id,
                        "react_thought",
                        iteration=ctx.iteration,
                        visibility="user",
                    )
                    raise RuntimeError(observation) from e

                await self._drain_stream_delta(stream_id)
                await self._end_llm_stream(
                    script_id,
                    conversation_id,
                    stream_id,
                    "react_thought",
                    iteration=ctx.iteration,
                    visibility="user",
                )

                # 计划回写改由显式 update_plan / replan 处理，不再每轮强制抽取

                if session.is_delegate_action(decision.action):
                    agent_id = str(
                        decision.action_input.get("agent_id", "")
                    ).strip()
                    step_type = resolve_step_for_roster_agent(
                        agent_id,
                        session._profile_id(),
                    )
                    if step_type and step_type in ctx.completed_step_types:
                        observation = (
                            f"步骤 {step_type} 已完成，请勿重复委派 agent_id={agent_id}。"
                        )
                        ctx.observations.append(observation)
                        session.observations = list(ctx.observations)
                        self._persist_master_react_turn(
                            conversation_id,
                            project_id,
                            script_id,
                            decision,
                            observation,
                        )
                        continue

                if decision.action == "finish":
                    self._persist_master_react_turn(
                        conversation_id,
                        project_id,
                        script_id,
                        decision,
                        str(
                            decision.action_input.get("observation", "主编排已完成。")
                        ),
                    )
                    await self._emit(
                        script_id,
                        "react_action",
                        self._react_action_payload(
                            decision, conversation_id, ctx.iteration
                        ),
                    )
                    finished_normally = True
                    break

                if decision.action in ("update_plan", "replan"):
                    await self._emit(
                        script_id,
                        "react_action",
                        self._react_action_payload(
                            decision, conversation_id, ctx.iteration
                        ),
                    )
                    from core.llm.tools.plan.handler import (
                        handle_replan,
                        handle_update_plan,
                    )
                    from core.llm.agent.react_core import AgentRunContext

                    plan_ctx = AgentRunContext(
                        task_brief=session.task_brief,
                        work_context={},
                        script_id=script_id,
                        step_id=script_id,
                        agent_name=MASTER_AGENT_NAME,
                        conversation_id=conversation_id,
                        project_id=project_id,
                    )
                    handler = (
                        handle_replan
                        if decision.action == "replan"
                        else handle_update_plan
                    )
                    result = handler(
                        self._store, plan_ctx, dict(decision.action_input or {})
                    )
                    observation = result.observation
                    if result.ok:
                        plan_warn = self._apply_master_plan_update(
                            session, plan, script_id, decision
                        )
                        if plan_warn:
                            observation = f"{observation}\n{plan_warn}"
                        # 重新加载 store 中的 plan（replan 已 version++）
                        refreshed = self._store.get_plan(script_id)
                        if refreshed is not None:
                            plan = refreshed
                        session.execution_plan = build_plan_snapshot(plan)
                        structured = result.structured or {}
                        await self._emit_plan_updated(
                            script_id,
                            conversation_id,
                            plan,
                            session,
                            include_full_plan=decision.action == "replan",
                            affected_step_ids=(
                                list(structured.get("affected_step_ids") or [])
                                if decision.action == "replan"
                                else None
                            ),
                            reason=(
                                str(structured.get("reason") or "")
                                if decision.action == "replan"
                                else None
                            ),
                        )
                        if decision.action == "replan":
                            await self._emit(
                                script_id,
                                "plan_ready",
                                {"plan": plan.model_dump()},
                            )
                    ctx.observations.append(observation)
                    session.observations = list(ctx.observations)
                    self._persist_master_react_turn(
                        conversation_id,
                        project_id,
                        script_id,
                        decision,
                        observation,
                    )
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
                    continue

                if decision.action == ASK_USER_QUESTION_ACTION:
                    if goal_mode:
                        observation = (
                            "目标模式下不可用 ask_user_question，请根据已有信息合理推断并继续。"
                        )
                        ctx.observations.append(observation)
                        session.observations = list(ctx.observations)
                        self._persist_master_react_turn(
                            conversation_id,
                            project_id,
                            script_id,
                            decision,
                            observation,
                        )
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
                        continue
                    await self._emit(
                        script_id,
                        "react_action",
                        self._react_action_payload(
                            decision, conversation_id, ctx.iteration
                        ),
                    )
                    from core.llm.tools.shared.ask_user import (
                        execute_ask_user_question,
                        merge_user_answers_into_brief,
                    )

                    values: dict[str, Any] = {}
                    try:
                        observation, values = await wait_or_cancel(
                            script_id,
                            execute_ask_user_question(
                                self._confirmation,
                                decision.action_input,
                                step_id=script_id,
                                conversation_id=conversation_id,
                            ),
                        )
                        if values:
                            session.task_brief = merge_user_answers_into_brief(
                                session.task_brief, values
                            )
                    except ExecutionCancelledError:
                        user_aborted = True
                        break
                    except Exception as e:
                        from core.llm.a2ui.manager import ConfirmationTimeoutError

                        if isinstance(e, ConfirmationTimeoutError):
                            observation = "用户确认超时，未收到回答。"
                        else:
                            observation = f"ask_user_question 失败：{e}"
                        values = {}
                    if user_aborted:
                        break
                    ctx.observations.append(observation)
                    session.observations = list(ctx.observations)
                    self._persist_master_react_turn(
                        conversation_id,
                        project_id,
                        script_id,
                        decision,
                        observation,
                    )
                    await self._emit(
                        script_id,
                        "react_observation",
                        {
                            "iteration": ctx.iteration,
                            "observation": observation,
                            "conversation_id": conversation_id,
                            "kind": "ask_user",
                            "user_values": values if values else None,
                        },
                    )
                    continue

                if decision.is_batch and all(
                    session.is_tool_action(c.action) for c in decision.calls
                ):
                    batch_mode = decision.batch_mode
                    await self._emit(
                        script_id,
                        "react_action_batch",
                        {
                            "iteration": ctx.iteration,
                            "conversation_id": conversation_id,
                            "actions": [
                                {
                                    "action": c.action,
                                    "action_input": dict(c.action_input or {}),
                                }
                                for c in decision.calls
                            ],
                            "batch_size": len(decision.calls),
                            "batch_mode": batch_mode,
                        },
                    )

                    async def _run_tool(call: ToolCallDecision) -> tuple[str, str, str | BaseException]:
                        """执行主编排单条 tool_*，普通异常作为结果返回。"""
                        try:
                            obs = await self._tool_executor.execute(
                                call.action,
                                script_id,
                                call.action_input,
                                session=session,
                                conversation_id=conversation_id,
                            )
                            return call.action, call.tool_call_id, obs
                        except Exception as e:
                            return call.action, call.tool_call_id, e

                    if batch_mode == "sequential":
                        tool_results = [await _run_tool(c) for c in decision.calls]
                    else:
                        tool_results = await asyncio.gather(
                            *[_run_tool(c) for c in decision.calls]
                        )
                    for call in decision.calls:
                        session.completed_tools.add(call.action.removeprefix("tool_"))
                    observation = self._persist_master_react_turn_batch(
                        conversation_id,
                        project_id,
                        script_id,
                        decision,
                        tool_results,
                    )
                    ctx.observations.append(observation)
                    session.observations = list(ctx.observations)
                    await self._emit(
                        script_id,
                        "react_observation",
                        {
                            "iteration": ctx.iteration,
                            "observation": observation,
                            "conversation_id": conversation_id,
                            "kind": "tool",
                            "batch_size": len(decision.calls),
                            "batch_mode": batch_mode,
                        },
                    )
                    continue

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
                            decision.action,
                            script_id,
                            decision.action_input,
                            session=session,
                            conversation_id=conversation_id,
                        )
                    except Exception as e:
                        observation = f"工具 {decision.action} 执行失败：{e}"
                    session.completed_tools.add(decision.action.removeprefix("tool_"))
                    ctx.observations.append(observation)
                    self._persist_master_react_turn(
                        conversation_id,
                        project_id,
                        script_id,
                        decision,
                        observation,
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
                    self._persist_master_react_turn(
                        conversation_id,
                        project_id,
                        script_id,
                        decision,
                        observation,
                    )
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

                from core.llm.master.delegate_deps import is_hard_blocked

                agent_id = str(
                    decision.action_input.get("agent_id", "")
                ).strip()
                hard_reason = is_hard_blocked(
                    self._store,
                    script_id,
                    style_mode,
                    agent_id,
                    profile_id=session._profile_id(),
                )
                if hard_reason:
                    observation = f"无法委派 {agent_id}：{hard_reason}"
                    ctx.observations.append(observation)
                    session.observations = list(ctx.observations)
                    self._persist_master_react_turn(
                        conversation_id,
                        project_id,
                        script_id,
                        decision,
                        observation,
                    )
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

                if not agent_id:
                    observation = "delegate_agent 缺少 agent_id 参数。"
                    ctx.observations.append(observation)
                    session.observations = list(ctx.observations)
                    self._persist_master_react_turn(
                        conversation_id,
                        project_id,
                        script_id,
                        decision,
                        observation,
                    )
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

                step_type = resolve_step_for_roster_agent(
                    agent_id,
                    session._profile_id(),
                )
                if not step_type:
                    observation = f"未知或不可委派的 agent_id: {agent_id}"
                    ctx.observations.append(observation)
                    session.observations = list(ctx.observations)
                    self._persist_master_react_turn(
                        conversation_id,
                        project_id,
                        script_id,
                        decision,
                        observation,
                    )
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

                image_text_cfg = resolve_image_text_config(project, self._llm_config)
                resolved_image_source = effective_image_source(image_text_cfg)

                if (
                    not goal_mode
                    and step_type == "image_gen"
                    and uses_image_text_pipeline(style_mode)
                    and should_prompt_image_source(image_text_cfg, style_mode)
                ):
                    try:
                        source_response = await wait_or_cancel(
                            script_id,
                            self._confirmation.request(
                                kind="image_source",
                                title="选择图片来源",
                                description=(
                                    "即将为角色、道具、场景文字资产批量配图。"
                                    "请选择 AI 生图或搜索配图。"
                                ),
                                components=[
                                    A2UIComponent(
                                        id="image_source",
                                        component="select",
                                        label="图片来源",
                                        value=ImageSourceMode.GENERATE.value,
                                        options=[
                                            {
                                                "label": "AI 批量生图",
                                                "value": ImageSourceMode.GENERATE.value,
                                            },
                                            {
                                                "label": "搜索配图",
                                                "value": ImageSourceMode.SEARCH.value,
                                            },
                                        ],
                                        required=True,
                                    ),
                                ],
                                conversation_id=conversation_id,
                            ),
                        )
                    except ExecutionCancelledError:
                        user_aborted = True
                        break
                    if not source_response.approved:
                        observation = "用户取消图片素材步骤。"
                        ctx.observations.append(observation)
                        self._persist_master_react_turn(
                            conversation_id,
                            project_id,
                            script_id,
                            decision,
                            observation,
                        )
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
                        continue
                    resolved_image_source = effective_image_source(
                        image_text_cfg,
                        str(source_response.values.get("image_source", "")),
                    )
                elif step_type == "image_gen" and uses_image_text_pipeline(style_mode):
                    resolved_image_source = effective_image_source(image_text_cfg)

                if self._confirmation.has_pending():
                    observation = "存在未完成的确认请求，跳过委派。"
                    ctx.observations.append(observation)
                    self._persist_master_react_turn(
                        conversation_id,
                        project_id,
                        script_id,
                        decision,
                        observation,
                    )
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
                    continue

                if not goal_mode and decision.action in CONFIRM_BEFORE_ACTION:
                    gate = CONFIRM_BEFORE_ACTION[decision.action]
                    try:
                        response = await wait_or_cancel(
                            script_id,
                            self._confirmation.request(
                                kind="generic",
                                title=gate.title,
                                description=gate.description,
                                conversation_id=conversation_id,
                            ),
                        )
                    except ExecutionCancelledError:
                        user_aborted = True
                        break
                    if not response.approved:
                        observation = f"用户取消执行 {decision.action}。"
                        ctx.observations.append(observation)
                        self._persist_master_react_turn(
                            conversation_id,
                            project_id,
                            script_id,
                            decision,
                            observation,
                        )
                        continue

                depends_on = [last_step_id] if last_step_id else []
                step = self._make_step(step_type, depends_on, profile_id=session._profile_id())
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

                step.status = StepStatus.RUNNING
                await self._emit(
                    script_id,
                    "step_started",
                    {"step_id": step.id, "step_type": step.type},
                )

                image_gen_abort: ImageGenerationAbortError | None = None
                return_to_master_abort: ReturnToMasterError | None = None
                edit_compose_abort: EditComposeMissingAssetsError | None = None

                agent = self._registry.get(step.agent)
                resume_context = self._conversations.pop_agent_suspend(
                    conversation_id, agent.name
                )

                task_brief = self._build_delegate_task_brief(
                    ctx, session, step_type, decision, resume_context=resume_context
                )
                plan_slice = build_plan_slice_for_step(
                    plan, step, session.last_remaining_plan
                )
                work_context = {
                    "project_id": project_id,
                    "script_id": script_id,
                    "style_mode": style_mode,
                    "generation_mode": generation_mode,
                    "execution_mode": resolved_execution.value,
                    "conversation_id": conversation_id,
                    "user_message": ctx.user_message,
                    "plan_slice": plan_slice.model_dump(),
                }
                if session.extra.get("skill_overlay"):
                    from core.llm.agent.config_manager import get_agent_config_manager
                    from core.llm.prompt.skills.allowlist import skill_overlay_for_agent

                    mgr = get_agent_config_manager()
                    filtered = skill_overlay_for_agent(
                        session.extra.get("skill_overlay"),
                        profile_id=session._profile_id(),
                        agent_name=agent.name,
                        skill_allowlists_by_profile=mgr.get_data().skill_allowlists_by_profile,
                    )
                    if filtered:
                        work_context["skill_overlay"] = filtered
                if uses_image_text_pipeline(style_mode):
                    work_context["image_text_config"] = image_text_cfg.model_dump()
                    if step_type == "image_gen":
                        work_context["image_source"] = resolved_image_source.value

                try:
                    outputs = await wait_or_cancel(
                        script_id,
                        agent.run(
                            task_brief=task_brief,
                            work_context=work_context,
                            script_id=script_id,
                            step_id=step.id,
                        ),
                    )
                    step.outputs = outputs
                    needs_confirm = (
                        step_type in CONFIRM_AFTER_STEP and require_script_approval
                    )
                    if needs_confirm:
                        step.status = StepStatus.AWAITING_CONFIRMATION
                        await self._emit(
                            script_id,
                            "step_awaiting_confirmation",
                            {
                                "step_id": step.id,
                                "step_type": step.type,
                                "kind": "script_structure",
                            },
                        )
                    else:
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
                except ExecutionCancelledError:
                    user_aborted = True
                    step.status = StepStatus.FAILED
                    step.error = "用户已中止执行"
                    await self._emit(
                        script_id,
                        "step_failed",
                        {"step_id": step.id, "error": step.error},
                    )
                    break
                except DuplicateActionAbortError as e:
                    step.status = StepStatus.FAILED
                    step.error = str(e)
                    await self._emit(
                        script_id,
                        "step_failed",
                        {"step_id": step.id, "error": str(e)},
                    )
                except ImageGenerationAbortError as e:
                    analysis = e.failure_analysis
                    if analysis is not None:
                        enriched = enrich_failure_names(
                            self._store, list(analysis.failures)
                        )
                        analysis = build_image_gen_failure_analysis(
                            enriched,
                            succeeded_count=analysis.succeeded_count,
                            total_count=analysis.total_count,
                        )
                        image_gen_abort = ImageGenerationAbortError(
                            e.action,
                            str(e),
                            failure_analysis=analysis,
                        )
                    else:
                        image_gen_abort = e
                    step.status = StepStatus.FAILED
                    step.error = str(image_gen_abort)
                    fail_payload: dict[str, Any] = {
                        "step_id": step.id,
                        "error": str(image_gen_abort),
                    }
                    if image_gen_abort.failure_analysis is not None:
                        fail_payload["image_gen_failures"] = (
                            image_gen_abort.failure_analysis.to_dict()
                        )
                    await self._emit(script_id, "step_failed", fail_payload)
                    if image_gen_abort.needs_upstream_prompt_adjustment():
                        ctx.completed_step_types.discard("script_design")
                except ReturnToMasterError as e:
                    return_to_master_abort = e
                    edit_compose_abort = (
                        e if isinstance(e, EditComposeMissingAssetsError) else None
                    )
                    step.status = StepStatus.PAUSED
                    step.error = str(e)
                    fail_payload: dict[str, Any] = {
                        "step_id": step.id,
                        "error": str(e),
                        "return_to_master": e.to_dict(),
                    }
                    if e.validation_report is not None:
                        fail_payload["edit_missing"] = e.validation_report.to_dict()
                    await self._emit(script_id, "step_paused", fail_payload)
                    if isinstance(e, EditComposeMissingAssetsError) and e.validation_report:
                        for upstream in upstream_steps_to_redo(
                            e.validation_report.missing_items
                        ):
                            ctx.completed_step_types.discard(upstream)
                    else:
                        for suggested_id in e.structured.get("suggested_agent_ids") or []:
                            upstream = resolve_step_for_roster_agent(
                                str(suggested_id),
                                session._profile_id(),
                            )
                            if upstream:
                                ctx.completed_step_types.discard(upstream)
                except TtsAbortError as e:
                    step.status = StepStatus.FAILED
                    step.error = str(e)
                    await self._emit(
                        script_id,
                        "step_failed",
                        {"step_id": step.id, "error": str(e)},
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
                elif step.status == StepStatus.AWAITING_CONFIRMATION:
                    observation = (
                        f"已委派 {agent.display_name}，步骤「{step.title}」"
                        "等待用户确认剧本结构。"
                    )
                elif step.status == StepStatus.PAUSED:
                    if return_to_master_abort:
                        observation = return_to_master_abort.to_master_observation()
                    else:
                        observation = (
                            f"已委派 {agent.display_name}，步骤「{step.title}」暂停，"
                            "等待主编排协调。"
                        )
                elif step.status == StepStatus.FAILED:
                    if image_gen_abort and image_gen_abort.failure_analysis:
                        observation = format_image_gen_failure_observation(
                            image_gen_abort.failure_analysis,
                            agent_display_name=agent.display_name,
                            step_title=step.title,
                        )
                    elif edit_compose_abort and edit_compose_abort.validation_report:
                        observation = format_edit_compose_failure_observation(
                            edit_compose_abort.validation_report,
                            agent_display_name=agent.display_name,
                            step_title=step.title,
                        )
                    else:
                        observation = (
                            f"委派 {agent.display_name} 失败：{step.error or '未知错误'}。"
                        )

                ctx.observations.append(observation)
                self._persist_master_react_turn(
                    conversation_id,
                    project_id,
                    script_id,
                    decision,
                    observation,
                )
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
                    if step_type in ("image_gen", "edit_compose"):
                        continue
                    break

                if (
                    step.status == StepStatus.AWAITING_CONFIRMATION
                    and step_type in CONFIRM_AFTER_STEP
                ):
                    gate = CONFIRM_AFTER_STEP[step_type]
                    summary_md = build_script_structure_summary(
                        self._store, script_id
                    )
                    response = await wait_or_cancel(
                        script_id,
                        self._confirmation.request(
                            kind="script_structure",
                            title=gate.title,
                            description=gate.description,
                            components=[
                                A2UIComponent(
                                    id="summary",
                                    component="markdown",
                                    label="剧本概要",
                                    value=summary_md,
                                ),
                            ],
                            step_id=step.id,
                            conversation_id=conversation_id,
                        ),
                    )
                    intent = str(
                        response.values.get(
                            "intent",
                            "continue" if response.approved else "abort",
                        )
                    )
                    if intent == "regenerate":
                        step.status = StepStatus.RUNNING
                        self._conversations.clear_agent_session(
                            conversation_id, step.agent
                        )
                        ctx.completed_step_types.discard(step_type)
                        feedback = str(response.values.get("feedback", "")).strip()
                        if feedback:
                            regen_obs = f"用户要求重新生成剧本：{feedback}"
                            ctx.observations.append(regen_obs)
                            session.observations = list(ctx.observations)
                            self._conversations.add_user_message(
                                conversation_id,
                                project_id,
                                script_id,
                                feedback,
                            )
                            self._conversations.add_orphan_observation(
                                conversation_id,
                                project_id,
                                script_id,
                                regen_obs,
                                channel="master",
                            )
                        continue
                    if intent == "abort":
                        user_aborted = True
                        break
                    if not response.approved:
                        break
                    step.status = StepStatus.COMPLETED
                    step.progress = 100
                    await self._emit(
                        script_id,
                        "step_resumed",
                        {
                            "step_id": step.id,
                            "outputs": [o.model_dump() for o in step.outputs],
                        },
                    )
                    ctx.completed_step_types.add(step_type)

            if user_aborted:
                script = self._store.get_script(script_id)
                if script and script.status == ScriptStatus.EXECUTING:
                    script.status = ScriptStatus.FAILED
                for step in plan.steps:
                    if step.status == StepStatus.RUNNING:
                        step.status = StepStatus.FAILED
                        step.error = "用户已中止执行"
                await self._emit(
                    script_id,
                    "execution_aborted",
                    {
                        "script_id": script_id,
                        "conversation_id": conversation_id,
                        "error": "用户已中止执行",
                    },
                )
            elif not finished_normally:
                script = self._store.get_script(script_id)
                if script and script.status == ScriptStatus.EXECUTING:
                    script.status = ScriptStatus.FAILED
                from core.llm.master.plan_resolution import has_blocking_plan_failures

                if not has_blocking_plan_failures(plan.steps):
                    await self._emit(
                        script_id,
                        "execution_failed",
                        {
                            "script_id": script_id,
                            "error": "主编排未正常结束（用户中止或达到最大迭代次数）",
                        },
                    )

            await self._finalize(script_id, plan)

            script = self._store.get_script(script_id)
            await self._emit(
                script_id,
                "react_finished",
                {
                    "iterations": ctx.iteration,
                    "status": script.status.value if script else ScriptStatus.FAILED.value,
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
            log_perf(
                "master.react",
                "主 Agent ReAct 结束",
                duration_ms=(time.perf_counter() - react_start) * 1000,
                script_id=script_id,
                iterations=ctx.iteration,
                status=script.status.value if script else "unknown",
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
            await self._emit(
                script_id,
                "react_finished",
                {
                    "iterations": ctx.iteration,
                    "status": script.status.value if script else ScriptStatus.FAILED.value,
                    "completed_steps": list(ctx.completed_step_types),
                    "conversation_id": conversation_id,
                },
            )
            log_stage(
                logger,
                "master.react",
                "主 Agent ReAct 异常结束",
                script_id=script_id,
                iterations=ctx.iteration,
                error=str(e),
            )
            log_perf(
                "master.react",
                "主 Agent ReAct 异常结束",
                duration_ms=(time.perf_counter() - react_start) * 1000,
                level="warning",
                script_id=script_id,
                iterations=ctx.iteration,
                error=type(e).__name__,
            )
            raise

    async def _finalize(self, script_id: str, plan: PlanDocument) -> None:
        script = self._store.get_script(script_id)
        if not script:
            return

        from core.llm.master.plan_resolution import (
            has_blocking_plan_failures,
            is_plan_effectively_complete,
        )

        if plan.steps and is_plan_effectively_complete(plan.steps):
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

        if has_blocking_plan_failures(plan.steps):
            script.status = ScriptStatus.FAILED
            await self._emitter.emit({"type": "execution_failed", "script_id": script_id})
            return

        if script.status == ScriptStatus.EXECUTING:
            script.status = ScriptStatus.FAILED
            await self._emitter.emit(
                {
                    "type": "execution_failed",
                    "script_id": script_id,
                    "error": "执行未完成",
                }
            )
