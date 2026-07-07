"""子 Agent 抽象基类：统一 ReAct 入口，决策与动作执行均走 LLM。"""

from typing import Any

from core.llm.a2ui.manager import ConfirmationManager
from core.conversation import ConversationStore
from core.llm.agent.llm_action import build_action_system_prompt, run_llm_action
from core.llm.agent.prompt_resolver import resolve_agent_prompts
from core.llm.agent.react_core import AgentRunContext, ReActDecision, ReActRunner
from core.llm.tools.shared.agent_tools import ad_hoc_actions, is_ask_user_question_action, pipeline_actions, read_actions
from core.llm.tools import get_tool_registry
from core.events.emitter import EventEmitter
from core.interaction_log.recorder import InteractionRecorder
from core.llm.client import LLMClient
from core.llm.react_decide import decide_sub_agent
from core.llm.settings import LLMConfigManager
from core.models.entities import ExecutionMode, StepOutput
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
        confirmation_manager: ConfirmationManager | None = None,
    ) -> None:
        from core.llm.agent.config_manager import AgentConfigManager

        self._store = store
        self._emitter = emitter
        self._conversations = conversations
        self._llm_config = llm_config
        self._llm_client = llm_client
        self._recorder = recorder
        self._agent_config = agent_config or AgentConfigManager()
        self._confirmation = confirmation_manager
        self._runner = ReActRunner(emitter, conversations)
        self._tool_registry = get_tool_registry()

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
        role = bundle.role_prompt
        overlay = ctx.work_context.get("skill_overlay") or {}
        agent_overlays = overlay.get("agent_overlays") or {}
        snippet = str(agent_overlays.get(self.name, "")).strip()
        if snippet:
            role = f"{role}\n\n## Skill 补充\n{snippet}"
        return role

    def resolve_action_system_prompt(self, ctx: AgentRunContext) -> str:
        """解析行动执行时的 system prompt（固定区：协议 + actions + hint）。"""
        from core.llm.agent.prompt_resolver import resolve_prompt_profile

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

    def _tool_args_ready(self, action: str, args: dict[str, Any]) -> bool:
        spec = self._tool_registry.get(action)
        if spec is None or spec.agent not in (self.name, "common"):
            return False
        required = list(spec.input_schema.get("required") or [])
        if "observation" in required and not str(args.get("observation", "")).strip():
            return False
        for key in required:
            if key == "observation":
                continue
            if args.get(key) is None:
                return False
            if key == "content" and isinstance(args.get(key), dict) and not args[key]:
                return False
        return True

    async def execute_action(self, action: str, ctx: AgentRunContext) -> str:
        """执行单个 Action 并返回 Observation 文本。"""
        ctx.last_action_ok = True
        if is_ask_user_question_action(action):
            if str(ctx.work_context.get("execution_mode", "")) == ExecutionMode.GOAL.value:
                ctx.last_action_ok = False
                return "目标模式下不可用 ask_user_question，请根据已有信息合理推断并继续。"
            if not self._confirmation:
                return "ask_user_question 不可用：未配置 ConfirmationManager。"
            from core.llm.tools.shared.ask_user import (
                execute_ask_user_question,
                merge_user_answers_into_brief,
            )

            observation, values = await execute_ask_user_question(
                self._confirmation,
                ctx.current_action_input,
                step_id=ctx.step_id,
                conversation_id=ctx.conversation_id,
            )
            if values:
                ctx.task_brief = merge_user_answers_into_brief(ctx.task_brief, values)
            ctx.last_user_values = values if values else None
            return observation

        spec = self._tool_registry.get(action)
        args = dict(ctx.current_action_input or {})
        if spec and (spec.agent == self.name or spec.agent == "common"):
            if spec.read_only or self._tool_args_ready(action, args):
                if not str(args.get("observation", "")).strip():
                    args["observation"] = f"执行 {action}"
                result = await self._tool_registry.call_tool(
                    action, args, ctx, self._store
                )
                ctx.last_tool_structured = result.structured if result.structured else None
                ctx.last_action_ok = result.ok
                if not result.ok:
                    return result.observation
                return result.observation

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
            llm_config=self._llm_config,
        )

    def get_ad_hoc_actions(self) -> list[str]:
        """可在任意时刻调用的写操作（更新、删除等）。"""
        actions = ad_hoc_actions(self.name)
        return actions

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
            store=self._store,
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
        wc = dict(work_context)
        wc["emitter"] = self._emitter
        return await self._runner.run_agent(
            agent_name=self.name,
            display_name=self.display_name,
            task_brief=task_brief,
            work_context=wc,
            script_id=script_id,
            step_id=step_id,
            decide=self.decide,
            act=self._act_with_log,
        )
