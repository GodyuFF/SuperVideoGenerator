"""LLM 驱动的子 Agent：ReAct 决策与动作执行均通过大模型。"""



from typing import Any



from core.llm.agent.base import ReActAgent

from core.llm.agent.react_core import AgentRunContext

from core.llm.master.actions import filter_storyboard_pipeline_actions, filter_video_pipeline_actions





class ScriptAgent(ReActAgent):

    name = "script_agent"

    display_name = "剧本 Agent"





class ImageAgent(ReActAgent):

    name = "image_agent"

    display_name = "图片 Agent"





class StoryboardAgent(ReActAgent):

    name = "storyboard_agent"

    display_name = "分镜 Agent"



    def resolve_action_pipeline(

        self,

        ctx: AgentRunContext,

        pipeline: list[str],

    ) -> list[str]:

        """故事书走 create_frames；AI 视频走 create_video_clips。"""

        return filter_storyboard_pipeline_actions(

            pipeline,

            ctx.work_context.get("style_mode"),

        )





class StoryboardRefineAgent(ReActAgent):

    name = "storyboard_refine_agent"

    display_name = "分镜复核 Agent"



    def get_action_pipeline(self) -> list[str]:

        return [

            "get_shot_details",

            "get_shot_asset_timing",

            "sync_actual_assets",

            "update_frames",

            "persist_review",

        ]





class VideoAgent(ReActAgent):

    name = "video_agent"

    display_name = "视频 Agent"



    def resolve_action_pipeline(

        self,

        ctx: AgentRunContext,

        pipeline: list[str],

    ) -> list[str]:

        """仅执行 scan → generate_video_clips，不创建 video_clip 或镜内关联。"""

        _ = ctx

        return filter_video_pipeline_actions(pipeline)





class TTSAgent(ReActAgent):

    name = "tts_agent"

    display_name = "配音 Agent"





class EditingAgent(ReActAgent):

    name = "editing_agent"

    display_name = "剪辑 Agent"


