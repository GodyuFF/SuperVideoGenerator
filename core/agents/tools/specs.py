"""子 Agent 工具规格定义（与 product-plan §8 Tool 接口对齐）。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentToolSpec:
    """Agent 可调用的逻辑工具。"""

    name: str
    description: str
    action: str | None = None  # 运行时 ReAct action 名
    read_only: bool = False  # True 表示只读查询，走 AgentToolExecutor
    ad_hoc: bool = False  # True 表示可在 ReAct 任意时刻调用的写操作（更新/删除等）


AGENT_TOOLS: dict[str, list[AgentToolSpec]] = {
    "script_agent": [
        AgentToolSpec(
            "script.parse_brief",
            "解析任务简报并通过 LLM 设计/写入剧本正文",
            "parse_brief",
        ),
        AgentToolSpec("script.create_plot", "创建剧情文字资产", "create_plot"),
        AgentToolSpec("script.create_character", "创建人物共享资产", "create_character"),
        AgentToolSpec("script.create_scene", "创建场景共享资产", "create_scene"),
        AgentToolSpec(
            "script.update_script",
            "更新剧本标题或 Markdown 正文",
            "update_script",
            ad_hoc=True,
        ),
        AgentToolSpec(
            "script.update_plot",
            "更新剧情文字资产（需 asset_id）",
            "update_plot",
            ad_hoc=True,
        ),
        AgentToolSpec(
            "script.update_character",
            "更新人物资产（需 asset_id）",
            "update_character",
            ad_hoc=True,
        ),
        AgentToolSpec(
            "script.update_scene",
            "更新场景资产（需 asset_id）",
            "update_scene",
            ad_hoc=True,
        ),
        AgentToolSpec(
            "script.delete_plot",
            "删除剧情资产（需 asset_id）",
            "delete_plot",
            ad_hoc=True,
        ),
        AgentToolSpec(
            "script.delete_character",
            "删除人物资产（需 asset_id）",
            "delete_character",
            ad_hoc=True,
        ),
        AgentToolSpec(
            "script.delete_scene",
            "删除场景资产（需 asset_id）",
            "delete_scene",
            ad_hoc=True,
        ),
        AgentToolSpec(
            "script.list_text_assets",
            "列出剧本相关文字资产及与剧本的关联",
            "list_text_assets",
            read_only=True,
        ),
    ],
    "image_agent": [
        AgentToolSpec("image.scan_text_assets", "扫描待生图文字资产", "scan_text_assets"),
        AgentToolSpec("image.generate_images", "为文字资产生成图片", "generate_images"),
        AgentToolSpec(
            "image.list_images",
            "列出已生成图片资产",
            "list_images",
            read_only=True,
        ),
    ],
    "storyboard_agent": [
        AgentToolSpec("storyboard.load_context", "加载剧本与资产上下文", "load_context"),
        AgentToolSpec("storyboard.create_shots", "设计镜头列表", "create_shots"),
        AgentToolSpec("storyboard.persist_plan", "保存视频计划稿", "persist_plan"),
        AgentToolSpec(
            "storyboard.get_plan",
            "读取当前视频计划稿",
            "get_plan",
            read_only=True,
        ),
    ],
    "video_agent": [
        AgentToolSpec("video.load_shots", "加载分镜镜头列表", "load_shots"),
        AgentToolSpec("video.generate_clips", "为镜头生成 AI 视频片段", "generate_clips"),
        AgentToolSpec(
            "video.list_videos",
            "列出已生成视频资产",
            "list_videos",
            read_only=True,
        ),
    ],
    "tts_agent": [
        AgentToolSpec("tts.extract_narration", "从计划稿提取旁白", "extract_narration"),
        AgentToolSpec("tts.synthesize", "合成 TTS 音频", "synthesize"),
        AgentToolSpec(
            "tts.list_audio",
            "列出配音资产",
            "list_audio",
            read_only=True,
        ),
    ],
    "editing_agent": [
        AgentToolSpec("edit.gather_media", "收集图片/视频/配音素材", "gather_media"),
        AgentToolSpec("edit.compose_final", "合成最终成片", "compose_final"),
        AgentToolSpec(
            "edit.list_final",
            "列出成片资产",
            "list_final",
            read_only=True,
        ),
    ],
}


def pipeline_actions(agent_name: str) -> list[str]:
    """写操作 / 流水线 action（ReAct 主流程）。"""
    return [
        t.action
        for t in AGENT_TOOLS.get(agent_name, [])
        if t.action and not t.read_only and not t.ad_hoc
    ]


def ad_hoc_actions(agent_name: str) -> list[str]:
    """可在任意时刻调用的写操作（更新、删除等）。"""
    return [
        t.action
        for t in AGENT_TOOLS.get(agent_name, [])
        if t.action and not t.read_only and t.ad_hoc
    ]


def read_actions(agent_name: str) -> list[str]:
    """只读查询 action（任意时刻可调用）。"""
    return [
        t.action
        for t in AGENT_TOOLS.get(agent_name, [])
        if t.action and t.read_only
    ]


def available_actions(agent_name: str) -> list[str]:
    """子 Agent ReAct 全部可选 action（不含 finish）。"""
    return pipeline_actions(agent_name) + ad_hoc_actions(agent_name) + read_actions(agent_name)


def is_read_only_action(agent_name: str, action: str) -> bool:
    for tool in AGENT_TOOLS.get(agent_name, []):
        if tool.action == action:
            return tool.read_only
    return False
