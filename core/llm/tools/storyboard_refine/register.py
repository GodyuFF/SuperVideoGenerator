"""storyboard_refine_agent tools 注册。"""



from core.llm.tools.register_helpers import register_handlers

from core.llm.tools.registry import ToolRegistry

from core.llm.tools.storyboard_refine.handler import HANDLERS as REFINE_HANDLERS



_STORYBOARD_REFINE_META: dict[str, tuple[str, str, str, str]] = {

    "check_refine_prerequisites": (

        "storyboard_refine_agent",

        "write_pipeline",

        "storyboard_refine.check_refine_prerequisites",

        "检查 frame/TTS/(ai_video)video 是否齐套；未齐套则回主编排",

    ),

    "get_shot_details": (

        "storyboard_refine_agent",

        "read",

        "storyboard_refine.get_shot_details",

        "查询分镜详情（plan / detail / 配图状态）",

    ),

    "get_shot_asset_timing": (

        "storyboard_refine_agent",

        "read",

        "storyboard_refine.get_shot_asset_timing",

        "查询镜头对应音频/视频时长；音频含各时段文字",

    ),

    "get_refine_plan": (

        "storyboard_refine_agent",

        "read",

        "storyboard_refine.get_refine_plan",

        "读取含 shot_detail 的视频计划稿",

    ),

    "sync_actual_assets": (

        "storyboard_refine_agent",

        "write_pipeline",

        "storyboard_refine.sync_actual_assets",

        "同步实测资产时长与规划偏差",

    ),

    "analyze_av_sync": (

        "storyboard_refine_agent",

        "write_ad_hoc",

        "storyboard_refine.analyze_av_sync",

        "分析/应用音画时长协调（分层自动修复或打回）",

    ),

    "review_and_restructure": (

        "storyboard_refine_agent",

        "write_ad_hoc",

        "storyboard_refine.review_and_restructure",

        "批量复核并重排分镜（拆分/合并/重排等跨镜操作）",

    ),

    "review_shot": (

        "storyboard_refine_agent",

        "write_ad_hoc",

        "storyboard_refine.review_shot",

        "单镜复核：增量 patch 子镜/音频/字幕时段 + display_instructions",

    ),

    "update_frames": (

        "storyboard_refine_agent",

        "write_pipeline",

        "storyboard_refine.update_frames",

        "将展示说明合并进 frame 资产",

    ),

    "persist_review": (

        "storyboard_refine_agent",

        "write_pipeline",

        "storyboard_refine.persist_review",

        "保存分镜复核结果",

    ),

}





def register_storyboard_refine_tools(registry: ToolRegistry) -> None:

    """注册分镜复核 Agent 全部 tools。"""

    register_handlers(registry, REFINE_HANDLERS, _STORYBOARD_REFINE_META)


