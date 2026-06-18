"""LLM ReAct 决策器：XML 协议与 LLM 交互，无规则回退。"""

from typing import Any

from core.agents.react_core import AgentRunContext, ReActDecision
from core.llm.client import LLMClient
from core.llm.settings import LLMConfigManager
from core.interaction_log.recorder import InteractionRecorder
from core.llm.xml_protocol import (
    REACT_SYSTEM_PROMPT,
    build_context_xml,
    parse_react_xml,
)
from core.llm.react_session import ReActSession
from core.llm.streaming import OnDelta
from core.logging.setup import get_logger, log_stage

logger = get_logger("core.llm.react_decider")


class LLMReActDecider:
    """统一 ReAct 决策：仅通过 LLM XML 决策。"""

    def __init__(
        self,
        config: LLMConfigManager,
        client: LLMClient,
        recorder: InteractionRecorder | None = None,
    ) -> None:
        self._config = config
        self._client = client
        self._recorder = recorder

    def _require_llm(self) -> None:
        if not self._config.is_llm_available():
            raise RuntimeError(
                "未配置 API Key 或已关闭 LLM ReAct，请在 AI 配置中填写 Key 并启用 LLM ReAct"
            )

    def _sanitize_action(self, action: str, allowed: list[str]) -> str:
        action = action.strip()
        if action in allowed:
            return action
        for a in allowed:
            if a.lower() == action.lower():
                return a
        raise ValueError(f"非法 action「{action}」，允许: {allowed}")

    async def decide_session(
        self,
        session: ReActSession,
        on_delta: OnDelta | None = None,
    ) -> ReActDecision:
        """基于 ReActSession，通过纯净 ReAct 类决策。"""
        from core.llm.react_session import bind_react_session

        react = bind_react_session(
            session,
            self._config,
            self._client,
            self._recorder,
        )
        return await react.decide(on_delta=on_delta)

    async def decide_agent(
        self,
        ctx: AgentRunContext,
        display_name: str,
        action_pipeline: list[str],
        role_prompt: str = "",
    ) -> ReActDecision:
        self._require_llm()
        available = list(action_pipeline) + ["finish"]

        extra: dict[str, Any] = {
            "agent": ctx.agent_name,
            "step_id": ctx.step_id,
            "iteration": ctx.iteration,
        }
        if ctx.work_context.get("style_mode") is not None:
            sm = ctx.work_context["style_mode"]
            extra["style_mode"] = str(sm.value if hasattr(sm, "value") else sm)

        context_xml = build_context_xml(
            role_description=role_prompt or f"你是{display_name}",
            task_brief=ctx.task_brief,
            available_actions=available,
            completed=list(ctx.completed_actions),
            observations=ctx.observations,
            extra=extra,
        )
        log_ctx = {
            "project_id": ctx.work_context.get("project_id", ""),
            "script_id": ctx.script_id,
            "agent_name": ctx.agent_name,
            "step_id": ctx.step_id,
            "role": "sub_agent",
            "iteration": ctx.iteration,
        }

        try:
            raw = await self._client.complete_xml_react(
                REACT_SYSTEM_PROMPT,
                context_xml,
                log_context=log_ctx,
            )
            decision = parse_react_xml(raw)
            try:
                decision.action = self._sanitize_action(decision.action, available)
            except ValueError as e:
                raise RuntimeError(str(e)) from e
            return decision
        except Exception as e:
            log_stage(logger, "llm.react", "子 Agent LLM 失败", agent=ctx.agent_name, error=str(e))
            raise
