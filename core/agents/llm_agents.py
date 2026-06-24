"""LLM 驱动的子 Agent：ReAct 决策与动作执行均通过大模型。"""

from core.agents.base import ReActAgent
from core.agents.llm_action import run_llm_action
from core.agents.react_core import AgentRunContext


class ScriptAgent(ReActAgent):
    name = "script_agent"
    display_name = "剧本 Agent"

    def get_action_pipeline(self) -> list[str]:
        return ["parse_brief", "create_plot", "create_character", "create_scene"]

    async def execute_action(self, action: str, ctx: AgentRunContext) -> str:
        return await run_llm_action(
            self._store,
            self._llm_client,
            agent_name=self.name,
            display_name=self.display_name,
            role_prompt=self.resolve_role_prompt(ctx),
            action=action,
            ctx=ctx,
            system_prompt=self.resolve_action_system_prompt(ctx),
        )


class ImageAgent(ReActAgent):
    name = "image_agent"
    display_name = "图片 Agent"

    def get_action_pipeline(self) -> list[str]:
        return ["scan_text_assets", "generate_images"]

    async def execute_action(self, action: str, ctx: AgentRunContext) -> str:
        return await run_llm_action(
            self._store,
            self._llm_client,
            agent_name=self.name,
            display_name=self.display_name,
            role_prompt=self.resolve_role_prompt(ctx),
            action=action,
            ctx=ctx,
            system_prompt=self.resolve_action_system_prompt(ctx),
        )


class StoryboardAgent(ReActAgent):
    name = "storyboard_agent"
    display_name = "分镜 Agent"

    def get_action_pipeline(self) -> list[str]:
        return ["load_context", "create_shots", "persist_plan"]

    async def execute_action(self, action: str, ctx: AgentRunContext) -> str:
        return await run_llm_action(
            self._store,
            self._llm_client,
            agent_name=self.name,
            display_name=self.display_name,
            role_prompt=self.resolve_role_prompt(ctx),
            action=action,
            ctx=ctx,
            system_prompt=self.resolve_action_system_prompt(ctx),
        )


class VideoAgent(ReActAgent):
    name = "video_agent"
    display_name = "视频 Agent"

    def get_action_pipeline(self) -> list[str]:
        return ["load_shots", "generate_clips"]

    async def execute_action(self, action: str, ctx: AgentRunContext) -> str:
        return await run_llm_action(
            self._store,
            self._llm_client,
            agent_name=self.name,
            display_name=self.display_name,
            role_prompt=self.resolve_role_prompt(ctx),
            action=action,
            ctx=ctx,
            system_prompt=self.resolve_action_system_prompt(ctx),
        )


class TTSAgent(ReActAgent):
    name = "tts_agent"
    display_name = "配音 Agent"

    def get_action_pipeline(self) -> list[str]:
        return ["extract_narration", "synthesize"]

    async def execute_action(self, action: str, ctx: AgentRunContext) -> str:
        return await run_llm_action(
            self._store,
            self._llm_client,
            agent_name=self.name,
            display_name=self.display_name,
            role_prompt=self.resolve_role_prompt(ctx),
            action=action,
            ctx=ctx,
            system_prompt=self.resolve_action_system_prompt(ctx),
        )


class EditingAgent(ReActAgent):
    name = "editing_agent"
    display_name = "剪辑 Agent"

    def get_action_pipeline(self) -> list[str]:
        return ["gather_media", "compose_final"]

    async def execute_action(self, action: str, ctx: AgentRunContext) -> str:
        return await run_llm_action(
            self._store,
            self._llm_client,
            agent_name=self.name,
            display_name=self.display_name,
            role_prompt=self.resolve_role_prompt(ctx),
            action=action,
            ctx=ctx,
            system_prompt=self.resolve_action_system_prompt(ctx),
        )
