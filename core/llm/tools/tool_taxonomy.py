"""工具分类：作用范围（scopes）与操作意义（operations），支持多标签。"""

from __future__ import annotations

from dataclasses import dataclass

from core.llm.tools.spec import ToolKind, ToolSpec


@dataclass(frozen=True)
class ToolTaxonomy:
    """单个 action 的展示分类与说明。"""

    scopes: tuple[str, ...]
    operations: tuple[str, ...]
    description: str


# action -> (scopes, operations, description)；description 为空时回退 Registry / 启发式
_ACTION_TAXONOMY: dict[str, tuple[tuple[str, ...], tuple[str, ...], str]] = {
    "parse_brief": (("script", "project"), ("create", "generate"), "解析任务简报并通过 LLM 设计/写入剧本正文"),
    "create_plot": (("plot",), ("create",), "创建剧情文字资产"),
    "create_character": (("character",), ("create",), "创建人物共享资产"),
    "create_scene": (("scene",), ("create",), "创建空镜背景板共享资产"),
    "create_prop": (("prop",), ("create",), "创建道具共享资产"),
    "update_script": (("script",), ("update",), "更新剧本标题或 Markdown 正文"),
    "update_plot": (("plot",), ("update",), "更新剧情文字资产"),
    "update_character": (("character",), ("update",), "更新人物资产"),
    "update_scene": (("scene",), ("update",), "更新场景资产"),
    "update_prop": (("prop",), ("update",), "更新道具资产"),
    "delete_plot": (("plot",), ("delete",), "删除剧情资产"),
    "delete_character": (("character",), ("delete",), "删除人物资产"),
    "delete_scene": (("scene",), ("delete",), "删除场景资产"),
    "delete_prop": (("prop",), ("delete",), "删除道具资产"),
    "list_text_assets": (
        ("script", "plot", "character", "scene", "prop", "frame"),
        ("read",),
        "跨范围只读盘点。查询：剧本 content_md 与元数据；本剧本可见文字资产"
        "（character/scene/prop/plot/frame）完整 content、traits、scope/linked 关系；"
        "每项 linked_media 数字媒体摘要。用于改删前获取 asset_id。",
    ),
    "scan_text_assets": (("image", "character", "scene", "prop", "frame"), ("read", "scan"), "扫描待生图文字资产"),
    "generate_images": (("image",), ("generate",), "为文字资产生成图片"),
    "search_images": (("image",), ("search",), "搜索并关联配图"),
    "sync_text_from_image": (("image", "character", "scene", "prop"), ("sync", "update"), "根据图片回写文字资产"),
    "list_images": (("image",), ("read",), "列出已生成图片资产"),
    "load_context": (
        ("script", "storyboard", "plan", "asset"),
        ("read",),
        "跨范围只读，供分镜设计。查询：剧本 content_md；plots/narration 剧情段落；"
        "人物/场景/道具/frame 配图状态（has_image、needs_generation、variants）；"
        "assets_with_images 可引用图摘要；voice_roles 音色。不含完整 content。",
    ),
    "create_shots": (("storyboard", "shot"), ("create",), "设计镜内多轨 Shot（sub_shots + audio_tracks）"),
    "create_frames": (("frame", "shot"), ("create",), "为每子镜创建剧本画面 frame 资产"),
    "create_video_clips": (("video_clip", "shot"), ("create",), "为每子镜创建 video_clip 文字资产"),
    "persist_plan": (("plan", "storyboard"), ("persist",), "保存视频计划稿"),
    "get_plan": (("plan", "storyboard"), ("read",), "读取当前视频计划稿"),
    "get_shot_details": (
        ("shot", "storyboard"),
        ("read",),
        "跨范围只读。查询：指定镜头的 VideoPlan 详设、frame/配图状态与绑定数字媒体。",
    ),
    "get_shot_asset_timing": (
        ("shot", "audio", "video"),
        ("read", "analyze"),
        "跨范围只读。查询：镜头关联音频/视频实测时长与旁白 text_segments。",
    ),
    "get_refine_plan": (("plan", "storyboard"), ("read",), "读取复核计划"),
    "check_refine_prerequisites": (
        ("shot", "image", "audio", "video"),
        ("analyze", "control"),
        "检查复核前置媒体齐套；未齐套则 return_to_master",
    ),
    "sync_actual_assets": (("shot", "audio", "video", "image"), ("sync",), "同步实际资产到计划稿"),
    "analyze_av_sync": (("shot", "audio", "video"), ("analyze", "sync"), "音画时长分层协调分析/应用"),
    "review_and_restructure": (("storyboard", "shot", "plan"), ("update", "analyze"), "批量复核并重构分镜结构"),
    "review_shot": (("storyboard", "shot"), ("update", "analyze"), "单镜复核：增量 patch 时段与展示说明"),
    "update_frames": (("frame", "shot"), ("update",), "更新镜头画面资产"),
    "persist_review": (("plan", "storyboard"), ("persist",), "保存复核后的计划稿"),
    "load_shots": (("shot", "video"), ("read",), "加载分镜镜头列表"),
    "generate_clips": (("video", "shot"), ("generate",), "为镜头生成 AI 视频片段"),
    "generate_from_timeline": (("video", "timeline"), ("generate",), "按剪辑 video 轨生成视频片段"),
    "list_videos": (("video",), ("read",), "列出已生成视频资产"),
    "extract_narration": (("audio", "plan", "script"), ("read", "generate"), "从计划稿提取旁白"),
    "synthesize": (("audio",), ("generate",), "合成 TTS 音频"),
    "list_audio": (("audio",), ("read",), "列出配音资产"),
    "load_edit_context": (
        ("timeline", "plan", "asset"),
        ("read",),
        "跨范围只读，供剪辑准备。查询：VideoPlan 分镜与镜头 resolved 素材、plots、"
        "图文资产配图、media 清单、edit_timeline 摘要。",
    ),
    "plan_edit_timeline": (("timeline", "plan"), ("create", "analyze"), "规划剪辑时间轴"),
    "validate_edit_assets": (
        ("timeline", "asset"),
        ("read", "validate"),
        "跨范围只读。查询：剪辑计划稿素材是否齐备（ready/missing_items/resolved_clips）。",
    ),
    "report_missing_assets": (
        ("timeline", "asset"),
        ("read",),
        "跨范围只读。查询：剪辑时间轴缺失的图片/视频/音频引用列表。",
    ),
    "get_edit_timeline": (("timeline",), ("read",), "读取当前剪辑时间轴"),
    "analyze_edit_timeline": (("timeline",), ("read", "analyze"), "分析时间轴结构与问题"),
    "gather_media": (
        ("timeline", "asset", "video", "audio", "image"),
        ("read",),
        "跨范围只读。查询：剪辑时间轴引用的图片/视频/配音数字媒体及 missing_refs。",
    ),
    "compose_final": (("timeline", "export"), ("compose", "generate"), "合成最终成片"),
    "list_final": (("export", "video"), ("read",), "列出成片资产"),
    "add_clip": (("timeline", "clip"), ("create",), "添加媒体片段到时间轴"),
    "update_clip": (("timeline", "clip"), ("update",), "修改片段属性"),
    "remove_clip": (("timeline", "clip"), ("delete",), "删除时间轴片段"),
    "apply_effect": (("timeline", "clip"), ("update",), "应用视觉效果"),
    "set_keyframe": (("timeline", "clip"), ("update",), "设置动画关键帧"),
    "export_timeline": (("timeline", "export"), ("export",), "导出成片视频"),
    "get_export_status": (("export",), ("read",), "查询导出进度"),
    "read_webpage": (("web",), ("read",), "读取指定 URL 网页正文"),
    "web_search": (("web",), ("read", "search"), "搜索网页信息"),
    "tool_get_plan_summary": (("plan",), ("read",), "查询计划摘要"),
    "tool_list_assets": (
        ("asset",),
        ("read",),
        "跨范围只读（主编排 tool_*）。查询：当前剧本全部文字资产与"
        "图片/音频/视频/成片数字媒体清单（含 URL 与可访问性）。",
    ),
    "tool_read_webpage": (("web",), ("read",), "读取网页正文"),
    "return_to_master": (("orchestration",), ("control",), "结束子 Agent 任务并返回主编排"),
    "finish": (("orchestration",), ("control",), "结束当前 ReAct 轮次"),
    "ask_user_question": (("orchestration",), ("control",), "向用户发起结构化确认或提问"),
    "delegate_agent": (("orchestration",), ("delegate",), "委派子 Agent（传入 agent_id）"),
}


def is_read_primary_tool(*, read_only: bool, operations: tuple[str, ...]) -> bool:
    """判断工具是否以读取为主要操作意义。"""
    if read_only:
        return True
    if not operations:
        return True
    return operations[0] in ("read", "scan", "validate", "analyze")


def is_multi_scope_read_tool(
    agent_name: str,
    action: str,
    *,
    read_only: bool = False,
    operations: tuple[str, ...] = (),
) -> bool:
    """跨多类持久化实体只读查询（工作台单独分组）。"""
    from core.llm.tools.tool_data_scope import resolve_tool_data_scope

    if not is_read_primary_tool(read_only=read_only, operations=operations):
        return False
    scope = resolve_tool_data_scope(agent_name, action, read_only=read_only)
    reads = tuple(e for e in scope.read_entities if "无" not in e)
    return len(reads) >= 2


def _infer_scopes(action: str) -> tuple[str, ...]:
    """从 action 名启发式推断作用范围。"""
    scopes: list[str] = []
    token_map = {
        "script": "script",
        "plot": "plot",
        "character": "character",
        "scene": "scene",
        "prop": "prop",
        "frame": "frame",
        "shot": "shot",
        "image": "image",
        "video": "video",
        "audio": "audio",
        "timeline": "timeline",
        "clip": "clip",
        "plan": "plan",
        "edit": "timeline",
        "export": "export",
        "narration": "audio",
        "brief": "project",
    }
    for token, scope in token_map.items():
        if token in action and scope not in scopes:
            scopes.append(scope)
    if action.startswith("tool_") or action.startswith("list_"):
        if "asset" not in scopes:
            scopes.append("asset")
    if action.startswith("delegate_") and "orchestration" not in scopes:
        scopes.append("orchestration")
    if not scopes:
        scopes.append("project")
    return tuple(scopes)


def _infer_operations(action: str, kind: ToolKind | None) -> tuple[str, ...]:
    """从 action 名与 ToolKind 启发式推断操作意义。"""
    if action.startswith("delegate_"):
        return ("delegate",)
    if action in ("finish", "ask_user_question", "return_to_master"):
        return ("control",)
    if action.startswith("list_") or action.startswith("get_") or action.startswith("scan_"):
        return ("read",)
    if action.startswith("create_") or action.startswith("add_"):
        return ("create",)
    if action.startswith("update_") or action.startswith("apply_") or action.startswith("set_"):
        return ("update",)
    if action.startswith("delete_") or action.startswith("remove_"):
        return ("delete",)
    if action.startswith("generate_") or action in ("synthesize", "compose_final"):
        return ("generate",)
    if action.startswith("search_") or action == "web_search":
        return ("search",)
    if action.startswith("sync_"):
        return ("sync",)
    if action.startswith("persist_"):
        return ("persist",)
    if action.startswith("analyze_") or action.startswith("validate_") or action.startswith("review_"):
        return ("analyze",)
    if action.startswith("export_"):
        return ("export",)
    if action.startswith("parse_") or action.startswith("extract_"):
        return ("read", "generate")
    if action.startswith("load_"):
        return ("read",)
    if action.startswith("plan_"):
        return ("create", "analyze")
    if kind == ToolKind.READ:
        return ("read",)
    if kind == ToolKind.WRITE_AD_HOC:
        return ("update",)
    if kind == ToolKind.WRITE_PIPELINE:
        return ("create",)
    return ("read",)


def resolve_tool_taxonomy(
    agent_name: str,
    action: str,
    *,
    description: str = "",
    kind: ToolKind | str | None = None,
) -> ToolTaxonomy:
    """解析 action 的作用范围、操作意义与用户可见说明。"""
    parsed_kind: ToolKind | None = None
    if isinstance(kind, ToolKind):
        parsed_kind = kind
    elif isinstance(kind, str):
        try:
            parsed_kind = ToolKind(kind)
        except ValueError:
            parsed_kind = None

    if action in _ACTION_TAXONOMY:
        scopes, operations, desc = _ACTION_TAXONOMY[action]
        return ToolTaxonomy(
            scopes=scopes,
            operations=operations,
            description=desc or description or action,
        )

    scopes = _infer_scopes(action)
    operations = _infer_operations(action, parsed_kind)
    if agent_name == "super_video_master" and action.startswith("delegate_"):
        scopes = tuple(dict.fromkeys((*scopes, "orchestration")))
        operations = ("delegate",)

    return ToolTaxonomy(
        scopes=scopes,
        operations=operations,
        description=description.strip() or action,
    )


def taxonomy_from_spec(spec: ToolSpec) -> ToolTaxonomy:
    """从 Registry ToolSpec 生成分类信息。"""
    return resolve_tool_taxonomy(
        spec.agent,
        spec.name,
        description=spec.description,
        kind=spec.kind,
    )


def lookup_tool_spec(action: str) -> ToolSpec | None:
    """按 action 名从 Registry 查找 ToolSpec（含 tool_ 前缀别名）。"""
    from core.llm.tools import get_tool_registry

    registry = get_tool_registry()
    spec = registry.get(action)
    if spec is None and action.startswith("tool_"):
        spec = registry.get(action.removeprefix("tool_"))
    return spec


def resolve_tool_schemas(
    action: str,
    spec: ToolSpec | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    """解析工具的 input/output JSON Schema（Registry 优先，回退 action 级 schema）。"""
    if spec is not None:
        return dict(spec.input_schema), dict(spec.output_schema)
    from core.llm.tools.register_helpers import output_schema_for
    from core.llm.tools.schemas import action_input_schema

    return dict(action_input_schema(action)), dict(output_schema_for(action))


def tool_public_view(
    *,
    agent_name: str,
    action: str,
    name: str,
    description: str = "",
    kind: str = "pipeline",
    read_only: bool = False,
    spec: ToolSpec | None = None,
) -> dict[str, object]:
    """组装 API / 工作台使用的工具展示字段。"""
    from core.llm.tools.tool_data_scope import tool_data_scope_view

    tax = taxonomy_from_spec(spec) if spec else resolve_tool_taxonomy(
        agent_name, action, description=description
    )
    if spec and not description:
        description = spec.description
    elif tax.description:
        description = tax.description
    data_scope = tool_data_scope_view(agent_name, action, read_only=read_only)
    multi_scope_read = is_multi_scope_read_tool(
        agent_name,
        action,
        read_only=read_only,
        operations=tuple(tax.operations),
    )
    input_schema, output_schema = resolve_tool_schemas(action, spec)
    return {
        "name": name,
        "action": action,
        "description": description,
        "kind": kind,
        "read_only": read_only,
        "scopes": list(tax.scopes),
        "operations": list(tax.operations),
        "multi_scope_read": multi_scope_read,
        "input_schema": input_schema,
        "output_schema": output_schema,
        **data_scope,
    }
