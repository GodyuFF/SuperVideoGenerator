"""子 Agent 抽象基类：统一 ReAct 入口，决策与动作执行均走 LLM。"""

from typing import Any

from core.conversation import ConversationStore
from core.agents.llm_action import build_action_system_prompt, run_llm_action
from core.agents.prompt_resolver import resolve_agent_prompts
from core.agents.react_core import AgentRunContext, ReActDecision, ReActRunner
from core.agents.tools.executor import AgentToolExecutor
from core.agents.tools.specs import ad_hoc_actions, is_read_only_action, pipeline_actions, read_actions
from core.events.emitter import EventEmitter
from core.interaction_log.recorder import InteractionRecorder
from core.llm.client import LLMClient
from core.llm.react_decide import decide_sub_agent
from core.llm.settings import LLMConfigManager
from core.models.entities import StepOutput
from core.store.memory import MemoryStore


class ReActAgent:
    """子 Agent 基类：仅接收主 Agent 任务简报，在隔离会话中 ReAct 执行。"""

    name: str
    display_name: str
    role_prompt: str = ""

    def __init__(
        self,
        store: MemoryStore,
        emitter: EventEmitter,
        conversations: ConversationStore,
        llm_config: LLMConfigManager,
        llm_client: LLMClient,
        recorder: InteractionRecorder | None = None,
        agent_config: Any | None = None,
    ) -> None:
        from core.agents.config_manager import AgentConfigManager

        self._store = store
        self._emitter = emitter
        self._conversations = conversations
        self._llm_config = llm_config
        self._llm_client = llm_client
        self._recorder = recorder
        self._agent_config = agent_config or AgentConfigManager()
        self._runner = ReActRunner(emitter, conversations)
        self._tool_executor = AgentToolExecutor(store)

    def resolve_role_prompt(self, ctx: AgentRunContext) -> str:
        """按项目配置、全局模式与视频风格解析当前 role_prompt。"""
        project_id = str(ctx.work_context.get("project_id", ""))
        project = self._store.get_project(project_id) if project_id else None
        style_mode = ctx.work_context.get("style_mode")
        bundle = resolve_agent_prompts(
            self.name,
            style_mode=style_mode,
            global_profiles=self._agent_config.get_profiles(),
            project=project,
        )
        return bundle.role_prompt

    def resolve_action_system_prompt(self, ctx: AgentRunContext) -> str:
        """解析行动执行时的 system prompt（固定区：协议 + actions + hint）。"""
        from core.agents.prompt_resolver import resolve_prompt_profile

        project_id = str(ctx.work_context.get("project_id", ""))
        project = self._store.get_project(project_id) if project_id else None
        style_mode = ctx.work_context.get("style_mode")
        profile = resolve_prompt_profile(
            self.name,
            style_mode=style_mode,
            global_profiles=self._agent_config.get_profiles(),
            project=project,
        )
        return build_action_system_prompt(self.name, profile)

    def get_action_pipeline(self) -> list[str]:
        """写操作流水线 action。"""
        return pipeline_actions(self.name)

    def get_read_actions(self) -> list[str]:
        """只读查询 action。"""
        return read_actions(self.name)

    async def execute_action(self, action: str, ctx: AgentRunContext) -> str:
        """执行单个 Action 并返回 Observation 文本。"""
        if is_read_only_action(self.name, action):
            return self._tool_executor.execute_by_action(self.name, action, ctx)
        return await run_llm_action(
            self._store,
            self._llm_client,
            conversations=self._conversations,
            agent_name=self.name,
            display_name=self.display_name,
            role_prompt=self.resolve_role_prompt(ctx),
            action=action,
            ctx=ctx,
            system_prompt=self.resolve_action_system_prompt(ctx),
        )

    def get_ad_hoc_actions(self) -> list[str]:
        """可在任意时刻调用的写操作（更新、删除等）。"""
        return ad_hoc_actions(self.name)

    async def decide(self, ctx: AgentRunContext) -> ReActDecision:
        role_prompt = self.resolve_role_prompt(ctx)
        return await decide_sub_agent(
            self._llm_client,
            self._llm_config,
            ctx,
            conversations=self._conversations,
            display_name=self.display_name,
            role_prompt=role_prompt,
            action_pipeline=self.get_action_pipeline(),
            read_actions=self.get_read_actions(),
            ad_hoc_actions=self.get_ad_hoc_actions(),
        )

    async def _act_with_log(self, action: str, ctx: AgentRunContext) -> str:
        observation = await self.execute_action(action, ctx)
        if self._recorder:
            await self._recorder.record_agent_action(
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
