"""子 Agent 工具规格定义（与 product-plan §8 Tool 接口对齐）。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentToolSpec:
    """Agent 可调用的逻辑工具。"""

    name: str
    description: str
    action: str | None = None  # 对应 ReAct action_pipeline 中的行动名


AGENT_TOOLS: dict[str, list[AgentToolSpec]] = {
    "script_agent": [
        AgentToolSpec("script.parse_brief", "解析任务简报并写入剧本正文", "parse_brief"),
        AgentToolSpec("script.create_plot", "创建剧情文字资产", "create_plot"),
        AgentToolSpec("script.create_character", "创建人物共享资产", "create_character"),
        AgentToolSpec("script.create_scene", "创建场景共享资产", "create_scene"),
        AgentToolSpec("script.list_text_assets", "列出剧本相关文字资产"),
    ],
    "image_agent": [
        AgentToolSpec("image.scan_text_assets", "扫描待生图文字资产", "scan_text_assets"),
        AgentToolSpec("image.generate", "为文字资产生成图片", "generate_images"),
        AgentToolSpec("image.list", "列出已生成图片资产"),
    ],
    "storyboard_agent": [
        AgentToolSpec("storyboard.load_context", "加载剧本与资产上下文", "load_context"),
        AgentToolSpec("storyboard.create_shots", "设计镜头列表", "create_shots"),
        AgentToolSpec("storyboard.persist_plan", "保存视频计划稿", "persist_plan"),
        AgentToolSpec("storyboard.get_plan", "读取当前视频计划稿"),
    ],
    "video_agent": [
        AgentToolSpec("video.load_shots", "加载分镜并估算费用", "load_shots"),
        AgentToolSpec("video.generate_clips", "为镜头生成 AI 视频片段", "generate_clips"),
        AgentToolSpec("video.list", "列出已生成视频资产"),
    ],
    "tts_agent": [
        AgentToolSpec("tts.extract_narration", "从计划稿提取旁白", "extract_narration"),
        AgentToolSpec("tts.synthesize", "合成 TTS 音频", "synthesize"),
        AgentToolSpec("tts.list", "列出配音资产"),
    ],
    "editing_agent": [
        AgentToolSpec("edit.gather_media", "收集图片/视频/配音素材", "gather_media"),
        AgentToolSpec("edit.compose", "合成最终成片", "compose_final"),
        AgentToolSpec("edit.list_final", "列出成片资产"),
    ],
}
