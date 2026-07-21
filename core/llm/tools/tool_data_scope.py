"""Tool 数据作用域：各 action 可读/可写的逻辑表（中文）与资产层级边界。"""

from __future__ import annotations

from dataclasses import dataclass

# 唯一允许写入「剪辑时间轴」的 Agent（Registry Tool）
EDIT_TIMELINE_WRITE_AGENT = "editing_agent"

TOOL_GOVERNANCE_RULES: tuple[str, ...] = (
    "剪辑时间轴（edit_timelines）的创建与更新仅允许 editing_agent 的剪辑域 Tool 执行。",
    "其余 Agent 的写操作不得调用 set_edit_timeline 或 patch_timeline。",
    "分镜/TTS/生图/生视频 Tool 仅写分镜计划稿·镜头、文字资产或数字媒体资产。",
    "用户通过 OpenCut 保存走 REST PATCH /edit-timeline，不属于 Agent Tool。",
    "只读 Tool 不得产生任何 store 写副作用。",
)


@dataclass(frozen=True)
class ToolDataScope:
    """单个 Tool 的数据边界说明。"""

    asset_layer: str
    read_entities: tuple[str, ...]
    write_entities: tuple[str, ...]
    boundary_note: str = ""


def _read(*entities: str) -> ToolDataScope:
    """构造只读作用域。"""
    layer = entities[0] if entities else "无持久化"
    return ToolDataScope(
        asset_layer=layer,
        read_entities=entities,
        write_entities=(),
    )


def _write(
    layer: str,
    writes: tuple[str, ...],
    *,
    reads: tuple[str, ...] = (),
    note: str = "",
) -> ToolDataScope:
    """构造读写作用域。"""
    return ToolDataScope(
        asset_layer=layer,
        read_entities=reads or writes,
        write_entities=writes,
        boundary_note=note,
    )


# action -> ToolDataScope；未列出的 action 由 resolve_tool_data_scope 启发式推断
_ACTION_DATA_SCOPE: dict[str, ToolDataScope] = {
    # —— 编排 / 系统 ——
    "finish": _read("无业务持久化"),
    "ask_user_question": _read("无业务持久化"),
    "return_to_master": _write("编排层", ("ReAct 执行计划",), note="步骤 PAUSED，不写资产表"),
    "delegate_agent": _write("编排层", ("ReAct 执行计划",), note="委派子 Agent"),
    "update_plan": _write("编排层", ("ReAct 执行计划",), note="回写 runtime_summary / remaining_plan"),
    "replan": _write("编排层", ("ReAct 执行计划",), note="version++ 与步骤结构调整"),
    "tool_get_plan_summary": _read("剧本", "ReAct 执行计划"),
    "tool_list_assets": _read("文字资产", "数字媒体资产"),
    "tool_read_webpage": _read("无持久化"),
    "read_webpage": _read("无持久化"),
    "web_search": _read("无持久化"),
    # —— script_agent ——
    "parse_brief": _write(
        "剧本层",
        ("剧本", "剧情文字资产", "人物/场景/道具文字资产", "资产引用边"),
        reads=("项目",),
    ),
    "create_plot": _write("文字资产层", ("剧情文字资产", "资产引用边")),
    "create_character": _write("文字资产层", ("人物文字资产", "资产引用边")),
    "create_scene": _write("文字资产层", ("场景文字资产", "资产引用边")),
    "create_prop": _write("文字资产层", ("道具文字资产", "资产引用边")),
    "update_script": _write("剧本层", ("剧本",)),
    "update_plot": _write("文字资产层", ("剧情文字资产",)),
    "update_character": _write("文字资产层", ("人物文字资产",)),
    "update_scene": _write("文字资产层", ("场景文字资产",)),
    "update_prop": _write("文字资产层", ("道具文字资产",)),
    "delete_plot": _write("文字资产层", ("剧情文字资产", "资产引用边")),
    "delete_character": _write("文字资产层", ("人物文字资产", "资产引用边")),
    "delete_scene": _write("文字资产层", ("场景文字资产", "资产引用边")),
    "delete_prop": _write("文字资产层", ("道具文字资产", "资产引用边")),
    "list_text_assets": _read("文字资产", "数字媒体资产"),
    # —— image_agent ——
    "scan_text_assets": _read("文字资产"),
    "generate_images": _write(
        "数字媒体资产层",
        ("图片数字资产", "媒体物理文件", "文字资产", "资产引用边", "分镜计划稿·镜头"),
        reads=("分镜计划稿",),
        note="仅回填镜内画面/视频轨 media，不写剪辑时间轴",
    ),
    "search_images": _write(
        "数字媒体资产层",
        ("图片数字资产", "文字资产", "资产引用边"),
    ),
    "sync_text_from_image": _write("文字资产层", ("文字资产",)),
    "list_images": _read("图片数字资产"),
    # —— storyboard_agent ——
    "load_context": _read("剧本", "文字资产", "数字媒体资产", "资产引用边"),
    "create_shots": _write("分镜计划层", ("分镜计划稿·镜头",), note="内存设计，persist_plan 落库"),
    "create_frames": _write("文字资产层", ("画面文字资产", "资产引用边")),
    "create_video_clips": _write("文字资产层", ("video_clip 文字资产", "资产引用边")),
    "persist_plan": _write("分镜计划层", ("分镜计划稿",)),
    "get_plan": _read("分镜计划稿"),
    # —— storyboard_refine_agent ——
    "get_shot_details": _read("分镜计划稿·镜头", "文字资产", "数字媒体资产"),
    "get_shot_asset_timing": _read("分镜计划稿·镜头", "数字媒体资产"),
    "get_refine_plan": _read("分镜计划稿"),
    "check_refine_prerequisites": _write(
        "编排层",
        (),
        reads=("分镜计划稿·镜头", "文字资产", "数字媒体资产"),
        note="未齐套时抛 ReturnToMaster，不写资产表",
    ),
    "sync_actual_assets": _write(
        "分镜计划层",
        ("分镜计划稿·镜头",),
        reads=("数字媒体资产",),
        note="绑定 TTS/对齐时长；禁止写剪辑时间轴",
    ),
    "analyze_av_sync": _write(
        "分镜计划层",
        ("分镜计划稿·镜头",),
        reads=("数字媒体资产",),
        note="音画分层协调；可写 sync_policy/playback_rate/need_regen",
    ),
    "review_and_restructure": _write("分镜计划层", ("分镜计划稿·镜头",)),
    "review_shot": _write("分镜计划层", ("分镜计划稿·镜头",)),
    "update_frames": _write("文字资产层", ("画面文字资产",)),
    "persist_review": _write("分镜计划层", ("分镜计划稿",)),
    # —— tts_agent ——
    "extract_narration": _read("分镜计划稿·镜头"),
    "synthesize": _write(
        "数字媒体资产层",
        ("音频数字资产", "媒体物理文件", "资产引用边", "分镜计划稿·镜头"),
        note="TTS 后 sync_plan_from_tts 仅写分镜，不写剪辑时间轴",
    ),
    "list_audio": _read("音频数字资产"),
    # —— video_agent ——
    "load_shots": _read("分镜计划稿·镜头"),
    "generate_clips": _write(
        "数字媒体资产层",
        ("视频数字资产", "媒体物理文件", "分镜计划稿·镜头"),
        note="不写剪辑时间轴",
    ),
    "generate_from_timeline": _write(
        "数字媒体资产层",
        ("视频数字资产", "分镜计划稿·镜头"),
        reads=("剪辑时间轴",),
        note="读时间轴生成视频，不写剪辑时间轴",
    ),
    "list_videos": _read("视频数字资产"),
    # —— editing_agent ——
    "load_edit_context": _read("分镜计划稿", "剪辑时间轴", "文字资产", "数字媒体资产"),
    "plan_edit_timeline": _write(
        "剪辑时间轴层",
        ("剪辑时间轴",),
        reads=("分镜计划稿", "数字媒体资产"),
        note="唯一流水线创建/合并全片时间轴",
    ),
    "validate_edit_assets": _read("剪辑时间轴", "数字媒体资产"),
    "report_missing_assets": _read("剪辑时间轴", "数字媒体资产"),
    "get_edit_timeline": _read("剪辑时间轴"),
    "analyze_edit_timeline": _read("剪辑时间轴"),
    "gather_media": _read("剪辑时间轴", "数字媒体资产"),
    "compose_final": _write(
        "数字媒体资产层",
        ("成片数字资产", "导出媒体文件"),
        reads=("剪辑时间轴",),
    ),
    "list_final": _read("成片数字资产"),
    "add_clip": _write(
        "剪辑时间轴层",
        ("剪辑时间轴", "分镜计划稿·镜头"),
        reads=("数字媒体资产",),
        note="patch_timeline；可创建空时间轴",
    ),
    "update_clip": _write("剪辑时间轴层", ("剪辑时间轴", "分镜计划稿·镜头")),
    "remove_clip": _write("剪辑时间轴层", ("剪辑时间轴", "分镜计划稿·镜头")),
    "apply_effect": _write("剪辑时间轴层", ("剪辑时间轴",)),
    "set_keyframe": _write("剪辑时间轴层", ("剪辑时间轴",)),
    "export_timeline": _read("剪辑时间轴"),
    "get_export_status": _read("导出任务"),
}


def _infer_scope(agent_name: str, action: str, *, read_only: bool) -> ToolDataScope:
    """对未显式登记的 action 做最小推断。"""
    if read_only or action.startswith(("get_", "list_", "load_", "scan_", "analyze_", "validate_")):
        return _read("项目域资产")
    if action.startswith("create_"):
        return _write("资产层", ("领域实体",))
    if action.startswith(("update_", "delete_", "remove_", "sync_", "persist_", "apply_", "set_")):
        return _write("资产层", ("领域实体",))
    if action.startswith(("generate_", "compose_", "synthesize", "parse_")):
        return _write("资产层", ("领域实体",))
    if agent_name == EDIT_TIMELINE_WRITE_AGENT:
        return _write("剪辑时间轴层", ("剪辑时间轴",))
    return _read("项目域资产")


def resolve_tool_data_scope(
    agent_name: str,
    action: str,
    *,
    read_only: bool = False,
) -> ToolDataScope:
    """解析 action 的中文数据作用域。"""
    if action in _ACTION_DATA_SCOPE:
        return _ACTION_DATA_SCOPE[action]
    return _infer_scope(agent_name, action, read_only=read_only)


def tool_data_scope_view(
    agent_name: str,
    action: str,
    *,
    read_only: bool = False,
) -> dict[str, object]:
    """供 API / 工具中心使用的 JSON 视图。"""
    scope = resolve_tool_data_scope(agent_name, action, read_only=read_only)
    writes_timeline = "剪辑时间轴" in scope.write_entities
    return {
        "asset_layer": scope.asset_layer,
        "affected_data_read": list(scope.read_entities),
        "affected_data_write": list(scope.write_entities),
        "boundary_note": scope.boundary_note,
        "may_write_edit_timeline": writes_timeline and agent_name == EDIT_TIMELINE_WRITE_AGENT,
    }


def governance_payload() -> dict[str, object]:
    """工具中心治理规则摘要。"""
    return {
        "edit_timeline_write_agent": EDIT_TIMELINE_WRITE_AGENT,
        "rules": list(TOOL_GOVERNANCE_RULES),
    }
