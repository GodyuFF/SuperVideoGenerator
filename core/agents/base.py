"""子 Agent 抽象基类：统一 ReAct 入口，与用户对话隔离，决策走 LLM XML。"""

from abc import ABC, abstractmethod
from typing import Any

from core.agents.conversation import ConversationStore
from core.agents.react_core import AgentRunContext, ReActDecision, ReActRunner
from core.events.emitter import EventEmitter
from core.interaction_log.recorder import InteractionRecorder
from core.llm.react_decider import LLMReActDecider
from core.models.entities import StepOutput
from core.store.memory import MemoryStore


class ReActAgent(ABC):
    """子 Agent 基类：仅接收主 Agent 任务简报，在隔离会话中 ReAct 执行。"""

    name: str
    display_name: str
    role_prompt: str = ""

    def __init__(
        self,
        store: MemoryStore,
        emitter: EventEmitter,
        conversations: ConversationStore,
        llm_decider: LLMReActDecider,
        recorder: InteractionRecorder | None = None,
    ) -> None:
        self._store = store
        self._emitter = emitter
        self._conversations = conversations
        self._llm_decider = llm_decider
        self._recorder = recorder
        self._runner = ReActRunner(emitter, conversations)

    @abstractmethod
    def get_action_pipeline(self) -> list[str]:
        """ReAct 行动序列（finish 前按序执行）。"""

    @abstractmethod
    async def execute_action(self, action: str, ctx: AgentRunContext) -> str:
        """执行单个 Action 并返回 Observation 文本。"""

    async def decide(self, ctx: AgentRunContext) -> ReActDecision:
        return await self._llm_decider.decide_agent(
            ctx,
            display_name=self.display_name,
            role_prompt=self.role_prompt,
            action_pipeline=self.get_action_pipeline(),
        )

    async def _act_with_log(self, action: str, ctx: AgentRunContext) -> str:
        observation = await self.execute_action(action, ctx)
        if self._recorder:
            await self._recorder.record_mock_action(
                script_id=ctx.script_id,
                project_id=str(ctx.work_context.get("project_id", "")),
                agent_name=self.name,
                step_id=ctx.step_id,
                action=action,
                observation=observation,
            )
        return observation

    async def run(
        self,
        task_brief: str,
        work_context: dict[str, Any],
        script_id: str,
        step_id: str,
    ) -> list[StepOutput]:
        """子 Agent 唯一入口：不接收用户原始对话。"""
        return await self._runner.run_agent(
            agent_name=self.name,
            display_name=self.display_name,
            task_brief=task_brief,
            work_context=work_context,
            script_id=script_id,
            step_id=step_id,
            decide=self.decide,
            act=self._act_with_log,
        )
