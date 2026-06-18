"""纯净 ReAct：Thought → Action → Observation，从 AI 配置加载 LLM。"""

from typing import Any, Awaitable, Callable

from core.agents.react_core import ReActDecision
from core.constants import MAX_REACT_ITERATIONS
from core.interaction_log.recorder import InteractionRecorder
from core.llm.client import LLMClient
from core.llm.react_models import (
    ReActAgentInfo,
    ReActStepRecord,
    ReActToolInfo,
    new_conversation_id,
)
from core.llm.settings import LLMConfigManager
from core.logging.setup import get_logger, log_stage

logger = get_logger("core.llm.react")

DEFAULT_MAX_ITERATIONS = MAX_REACT_ITERATIONS

ActionHandler = Callable[[str, dict[str, Any]], Awaitable[str]]
FallbackDecider = Callable[["ReAct"], ReActDecision]
ActionProvider = Callable[[], list[str]]
CompletedProvider = Callable[[], list[str]]

# 重导出模型，便于 `from core.llm.react import ...`
__all__ = [
    "ReAct",
    "ReActAgentInfo",
    "ReActToolInfo",
    "ReActStepRecord",
    "new_conversation_id",
    "ActionHandler",
    "FallbackDecider",
]


class ReAct:
    """
    纯净 ReAct 循环。

    核心参数：agent_name、conversation_id、agent、tools。
    LLM 连接信息从 LLMConfigManager（AI 配置）加载；也可注入已构造的 LLMClient。
    """

    def __init__(
        self,
        agent_name: str,
        conversation_id: str,
        agent: ReActAgentInfo,
        tools: list[ReActToolInfo],
        task_brief: str = "",
        llm_config: LLMConfigManager | None = None,
        llm_client: LLMClient | None = None,
        interaction_recorder: InteractionRecorder | None = None,
        extra_actions: list[str] | None = None,
        action_provider: ActionProvider | None = None,
        completed_provider: CompletedProvider | None = None,
        fallback: FallbackDecider | None = None,
        log_context: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
        user_summary: str = "",
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        react_session: Any = None,
    ) -> None:
        self.agent_name = agent_name
        self.conversation_id = conversation_id
        self.agent = agent
        self.tools = tools
        self.task_brief = task_brief
        self.extra_actions = list(extra_actions or [])
        self.extra = dict(extra or {})
        self.user_summary = user_summary
        self.max_iterations = max_iterations

        self._llm_config = llm_config or LLMConfigManager()
        self._llm_client = llm_client or LLMClient(
            self._llm_config, interaction_recorder
        )
        self._recorder = interaction_recorder
        self._action_provider = action_provider
        self._completed_provider = completed_provider
        self._fallback = fallback
        self._log_context = dict(log_context or {})

        self.observations: list[str] = []
        self.completed: set[str] = set()
        self.iteration: int = 0
        self.history: list[ReActStepRecord] = []
        self._react_session: Any = react_session

    @property
    def ai_config(self) -> dict[str, Any]:
        """当前 AI 配置快照（provider、model、是否可用等）。"""
        return self._llm_config.get_public_config()

    def is_tool_action(self, action: str) -> bool:
        return action.startswith("tool_")

    def available_actions(self) -> list[str]:
        if self._action_provider is not None:
            return self._action_provider()
        actions: list[str] = []
        for tool in self.tools:
            if tool.action_name not in self.completed:
                actions.append(tool.action_name)
        for action in self.extra_actions:
            if action not in self.completed:
                actions.append(action)
        actions.append("finish")
        return actions

    def completed_labels(self) -> list[str]:
        if self._completed_provider is not None:
            return self._completed_provider()
        return sorted(self.completed)

    def to_context_xml(self) -> str:
        from core.llm.xml_protocol import build_pure_react_xml

        if self._react_session is not None:
            from core.llm.xml_protocol import build_react_session_xml

            self._react_session.observations = list(self.observations)
            self._react_session.iteration = self.iteration
            return build_react_session_xml(self._react_session)
        return build_pure_react_xml(
            conversation_id=self.conversation_id,
            agent_name=self.agent_name,
            agent=self.agent,
            tools=self.tools,
            task_brief=self.task_brief,
            available_actions=self.available_actions(),
            completed=self.completed_labels(),
            observations=self.observations,
            extra=self.extra,
            user_summary=self.user_summary,
        )

    def _sanitize_action(self, action: str, allowed: list[str]) -> str:
        action = action.strip()
        if action in allowed:
            return action
        for candidate in allowed:
            if candidate.lower() == action.lower():
                return candidate
        raise ValueError(f"非法 action「{action}」，允许: {allowed}")

    async def _record_rule_fallback(self, reason: str) -> None:
        if not self._recorder:
            return
        await self._recorder.record_rule_fallback(
            script_id=str(self._log_context.get("script_id", "")),
            project_id=str(self._log_context.get("project_id", "")),
            agent_name=self.agent_name,
            step_id=str(self._log_context.get("step_id", "")),
            reason=reason,
            iteration=self.iteration,
        )

    async def decide(self) -> ReActDecision:
        """单轮推理：LLM XML 决策，失败时走 fallback。"""
        from core.llm.xml_protocol import REACT_SYSTEM_PROMPT, parse_react_xml

        allowed = self.available_actions()

        if not self._llm_config.is_llm_available():
            reason = "未配置 API Key 或已关闭 LLM ReAct"
            await self._record_rule_fallback(reason)
            if self._fallback:
                return self._fallback(self)
            return ReActDecision(
                thought="LLM 不可用，结束 ReAct。",
                action="finish",
            )

        context_xml = self.to_context_xml()
        log_ctx = {
            **self._log_context,
            "conversation_id": self.conversation_id,
            "agent_name": self.agent_name,
            "iteration": self.iteration,
        }

        try:
            raw = await self._llm_client.complete_xml_react(
                REACT_SYSTEM_PROMPT,
                context_xml,
                log_context=log_ctx,
            )
            decision = parse_react_xml(raw)
            decision.action = self._sanitize_action(decision.action, allowed)
            return decision
        except Exception as e:
            log_stage(
                logger,
                "llm.react",
                "ReAct LLM 回退",
                agent=self.agent_name,
                error=str(e),
            )
            await self._record_rule_fallback(str(e))
            if self._fallback:
                return self._fallback(self)
            return ReActDecision(
                thought=f"LLM 决策失败：{e}",
                action="finish",
            )

    async def run(self, on_action: ActionHandler) -> list[ReActStepRecord]:
        """
        执行完整 ReAct 循环：decide → on_action → observation。
        on_action 负责执行 tool / 委派等行动并返回 Observation 文本。
        """
        self.history.clear()

        for _ in range(self.max_iterations):
            self.iteration += 1
            decision = await self.decide()

            record = ReActStepRecord(
                iteration=self.iteration,
                thought=decision.thought,
                action=decision.action,
                action_input=dict(decision.action_input),
            )
            self.history.append(record)

            if decision.action == "finish":
                break

            observation = await on_action(decision.action, decision.action_input)
            record.observation = observation
            self.observations.append(observation)
            self.completed.add(decision.action)

        return self.history

    @classmethod
    def from_ai_config(
        cls,
        agent_name: str,
        conversation_id: str,
        agent: ReActAgentInfo,
        tools: list[ReActToolInfo],
        llm_config: LLMConfigManager,
        interaction_recorder: InteractionRecorder | None = None,
        **kwargs: Any,
    ) -> "ReAct":
        """从 AI 配置管理器构造 ReAct（自动创建 LLMClient）。"""
        client = LLMClient(llm_config, interaction_recorder)
        return cls(
            agent_name=agent_name,
            conversation_id=conversation_id,
            agent=agent,
            tools=tools,
            llm_config=llm_config,
            llm_client=client,
            interaction_recorder=interaction_recorder,
            **kwargs,
        )
