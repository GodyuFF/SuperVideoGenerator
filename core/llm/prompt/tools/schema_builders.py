"""从领域模型构建 action input_schema。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from core.models.image_text_asset import (
    CharacterContent,
    CharacterTraits,
    FrameContent,
    PropContent,
    PropTraits,
    SceneContent,
    SceneTraits,
)
from core.models.video_text_asset import VideoClipContent

_OBSERVATION: dict[str, Any] = {
    "type": "string",
    "description": "给 ReAct 循环的简短观察说明（中文）",
}


def _model_properties(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    return dict(schema.get("properties", {}))


def _object_schema(
    properties: dict[str, Any],
    *,
    required: list[str] | None = None,
    description: str = "",
    additional_properties: bool = False,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": additional_properties,
    }
    if description:
        out["description"] = description
    if required:
        out["required"] = required
    return out


def _partial_object_schema(
    properties: dict[str, Any],
    *,
    description: str = "",
    min_properties: int = 1,
    additional_properties: bool = True,
) -> dict[str, Any]:
    """部分更新 schema：不强制全部字段，但至少提供 min_properties 项。"""
    out: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "minProperties": min_properties,
        "additionalProperties": additional_properties,
    }
    if description:
        out["description"] = description
    return out


def build_script_brief_action_schema() -> dict[str, Any]:
    """parse_brief 行动 schema（创建/写入剧本正文）。"""
    return _object_schema(
        {
            "observation": _OBSERVATION,
            "title": {
                "type": "string",
                "description": "剧本标题",
            },
            "duration_sec": {
                "type": "integer",
                "minimum": 1,
                "description": "目标时长（秒）",
            },
            "content_md": {
                "type": "string",
                "description": (
                    "剧本 Markdown 正文；建议含 # 标题、## 场次/段落、人物与场景描述"
                ),
            },
        },
        required=["observation", "content_md"],
        additional_properties=True,
    )


def build_script_update_action_schema() -> dict[str, Any]:
    """update_script：部分更新剧本字段，不要求每次提供 content_md。"""
    return _object_schema(
        {
            "observation": _OBSERVATION,
            "title": {
                "type": "string",
                "description": "剧本标题（可选）",
            },
            "duration_sec": {
                "type": "integer",
                "minimum": 1,
                "description": "目标时长（秒，可选）",
            },
            "content_md": {
                "type": "string",
                "description": "剧本 Markdown 正文（可选，有则合并替换）",
            },
        },
        required=["observation"],
        additional_properties=True,
    )


def build_plot_content_schema() -> dict[str, Any]:
    return _object_schema(
        {"text": {"type": "string", "description": "剧情段落正文"}},
        required=["text"],
        additional_properties=True,
    )


def build_plot_content_update_schema() -> dict[str, Any]:
    return _partial_object_schema(
        {"text": {"type": "string", "description": "剧情段落正文"}},
        description="要合并更新的剧情字段，至少提供一项",
    )


def _prompt_excluded_fields() -> frozenset[str]:
    return frozenset(
        {
            "image_prompt",
            "negative_prompt",
            "prompt_version",
            "prompt_locked",
            "tags",
            "display_mode",
            "notes",
            "image_variants",
        }
    )


def _required_image_text_fields(traits_model: type[BaseModel]) -> list[str]:
    base = ["summary", "description", "prompt_hint", "visual_style", "color_palette"]
    traits = [k for k in traits_model.model_fields if k not in _prompt_excluded_fields()]
    return base + traits


def _image_text_content_hints(props: dict[str, Any]) -> dict[str, Any]:
    for key, hint in {
        "description": "主视觉描述（≥80字，面向生图）",
        "summary": "卡片一句话摘要",
        "prompt_hint": "生图增强补充（光影、构图、镜头语言等）",
    }.items():
        if key in props and isinstance(props[key], dict):
            props[key]["description"] = hint
    return props


def _build_image_text_content_update_schema(
    content_model: type[BaseModel],
    *,
    description: str,
) -> dict[str, Any]:
    props = _image_text_content_hints(_model_properties(content_model))
    return _partial_object_schema(
        props,
        description=description,
        min_properties=1,
    )


def build_image_variant_item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["base", "expression", "pose", "action", "costume", "other"],
                "description": "base=设定主形象；其余为表情/姿态/动作变体",
            },
            "label": {"type": "string", "description": "变体短标签"},
            "meaning": {"type": "string", "description": "剧本语境/镜头用途"},
            "variant_prompt": {
                "type": "string",
                "description": "变体专属生图描述（不含完整人设）",
            },
        },
        "required": ["kind", "label", "variant_prompt"],
        "additionalProperties": False,
    }


def _inject_image_variants(props: dict[str, Any]) -> dict[str, Any]:
    props = dict(props)
    props["image_variants"] = {
        "type": "array",
        "description": "多图变体：description 为设定主形象；按剧本填写 expression/pose/action 变体（勿把多种表情堆进 description）",
        "items": build_image_variant_item_schema(),
        "maxItems": 8,
    }
    return props


def build_character_content_schema() -> dict[str, Any]:
    props = _inject_image_variants(
        _image_text_content_hints(_model_properties(CharacterContent))
    )
    if "tts_voice" in props and isinstance(props["tts_voice"], dict):
        field = dict(props["tts_voice"])
        field["description"] = (
            "角色 TTS 配音音色；必须从编排状态 tts_available_voices 中选择，"
            "并与 gender 性别匹配（-Female/-Male 后缀或 OpenAI 音色名）"
        )
        props["tts_voice"] = field
    return _object_schema(
        props,
        required=_required_image_text_fields(CharacterTraits),
        description="人物图文资产 content；image_prompt 由系统自动组装，勿手写",
        additional_properties=True,
    )


def build_character_content_update_schema() -> dict[str, Any]:
    return _build_image_text_content_update_schema(
        CharacterContent,
        description="人物 content 部分更新字段（合并到现有资产），至少提供一项",
    )


def _scene_schema_properties() -> dict[str, Any]:
    props = _inject_image_variants(_model_properties(SceneContent))
    _field_desc: dict[str, str] = {
        "summary": "空镜背景板一句话摘要（仅环境，无人物）",
        "description": (
            "空镜背景板主视觉描写（≥80字）；仅无人环境：空间、光线、天气、材质、固定陈设。"
            "禁止人物/动物/角色/叙事动作/独立道具主体"
        ),
        "prompt_hint": "光影、构图、镜头、景深；禁止人物/动物/动作相关词",
        "key_objects": "环境固定陈设 only（墙/窗/天际线/地面等），非 prop 资产，非人物相关物",
        "foreground": "前景环境元素 only（材质/地面/雾气等），无人物无道具主体",
        "background": "远景环境 only，无人物剪影",
    }
    for key, desc in _field_desc.items():
        if key not in props:
            continue
        field = dict(props[key]) if isinstance(props[key], dict) else {"type": "string"}
        field["description"] = desc
        props[key] = field
    return props


def build_scene_content_schema() -> dict[str, Any]:
    return _object_schema(
        _scene_schema_properties(),
        required=_required_image_text_fields(SceneTraits),
        description=(
            "空镜背景板（scene）content；仅无人环境，供 frame 图生图合成参考。"
            "无信息字段填「未指定」；不要填写 image_variants"
        ),
        additional_properties=True,
    )


def build_scene_content_update_schema() -> dict[str, Any]:
    return _build_image_text_content_update_schema(
        SceneContent,
        description="空镜 content 部分更新字段（合并到现有资产），至少提供一项",
    )


def build_prop_content_schema() -> dict[str, Any]:
    props = _inject_image_variants(_model_properties(PropContent))
    return _object_schema(
        props,
        required=_required_image_text_fields(PropTraits),
        description="道具/物品图文资产 content；无信息字段填「未指定」",
        additional_properties=True,
    )


def build_prop_content_update_schema() -> dict[str, Any]:
    return _build_image_text_content_update_schema(
        PropContent,
        description="道具 content 部分更新字段（合并到现有资产），至少提供一项",
    )


def build_frame_content_schema() -> dict[str, Any]:
    """剧本画面 frame content：名称侧字段外，仅 summary / image_prompt / notes / element_refs。"""
    full = _model_properties(FrameContent)
    keep = ("summary", "image_prompt", "notes", "element_refs", "prompt_locked")
    props = {k: full[k] for k in keep if k in full}
    for key, desc in {
        "summary": "一句话摘要",
        "image_prompt": "生图提示词（≥80字，面向生图；用户/Agent 直接填写）",
        "notes": "AI 编排自用备注，不进入生图提示词",
        "element_refs": "关联角色/空镜/物品/画面资产",
    }.items():
        if key in props and isinstance(props[key], dict):
            field = dict(props[key])
            field["description"] = desc
            props[key] = field
    return _object_schema(
        props,
        required=["summary", "image_prompt"],
        description="剧本画面 frame 精简 content（summary / image_prompt / notes / element_refs）",
        additional_properties=True,
    )


def _video_clip_element_refs_schema() -> dict[str, Any]:
    """video_clip 仅允许关联画面 frame。"""
    return {
        "type": "object",
        "description": "仅关联画面 frame 文字资产 ID；禁止 character/scene/prop",
        "properties": {
            "frame": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    }


def build_video_clip_content_schema() -> dict[str, Any]:
    """video_clip content：仅 summary / video_prompt / notes / element_refs（系统字段可额外写入）。"""
    full = _model_properties(VideoClipContent)
    keep = ("summary", "video_prompt", "notes", "element_refs", "prompt_locked")
    props = {k: full[k] for k in keep if k in full}
    if "element_refs" in props:
        props["element_refs"] = _video_clip_element_refs_schema()
    for key, desc in {
        "video_prompt": "生视频提示词（≥80字）",
        "summary": "一句话摘要",
        "notes": "AI 编排自用备注，不进入生视频提示词",
    }.items():
        if key in props and isinstance(props[key], dict):
            field = dict(props[key])
            field["description"] = desc
            props[key] = field
    return _object_schema(
        props,
        required=["summary", "video_prompt"],
        description="video_clip 精简 content（summary / video_prompt / notes / element_refs）",
        additional_properties=True,
    )


def build_text_asset_draft_tool_input_schema() -> dict[str, Any]:
    """工作台专用 generate_text_asset_draft 输入（不注册 Agent ToolRegistry）。"""
    return _object_schema(
        {
            "asset_type": {
                "type": "string",
                "enum": ["character", "scene", "prop", "frame", "video_clip"],
                "description": "图文资产类型",
            },
            "summary": {
                "type": "string",
                "description": "用户摘要或创意要点（必填，可据此生成完整字段）",
            },
            "name": {
                "type": "string",
                "description": "可选资产名称；缺省时由模型建议",
            },
            "hints": {
                "type": "object",
                "description": "用户已填写的部分字段，生成时应保留或在此基础上补全",
                "additionalProperties": True,
            },
        },
        required=["asset_type", "summary"],
        description="工作台一键 AI 生成图文资产草稿",
        additional_properties=False,
    )


def build_text_asset_draft_tool_output_schema() -> dict[str, Any]:
    """工作台 generate_text_asset_draft 输出：资产名称 + 完整 content。"""
    return _object_schema(
        {
            "name": {"type": "string", "description": "资产显示名称"},
            "content": {
                "type": "object",
                "description": "与 asset_type 匹配的完整 content JSON",
                "additionalProperties": True,
            },
        },
        required=["name", "content"],
        description="生成的图文资产草稿",
        additional_properties=False,
    )


def draft_content_schema_for_type(asset_type: str) -> dict[str, Any]:
    """按资产类型返回草稿 content 的 JSON Schema（写入 LLM 提示）。"""
    builders = {
        "character": build_character_content_schema,
        "scene": build_scene_content_schema,
        "prop": build_prop_content_schema,
        "frame": build_frame_content_schema,
        "video_clip": build_video_clip_content_schema,
    }
    builder = builders.get(asset_type)
    if builder is None:
        raise ValueError(f"不支持的资产类型: {asset_type}")
    return builder()


def build_read_only_query_schema(*, description: str = "") -> dict[str, Any]:
    """只读 list/get 工具：仅需 observation。"""
    return _object_schema(
        {
            "observation": _OBSERVATION,
            "note": {
                "type": "string",
                "description": "可选查询说明",
            },
        },
        required=["observation"],
        description=description,
        additional_properties=False,
    )


def build_list_text_assets_input_schema() -> dict[str, Any]:
    """list_text_assets 专用输入：observation + 可选类型过滤与 content 开关。"""
    return _object_schema(
        {
            "observation": _OBSERVATION,
            "types": {
                "type": "array",
                "description": "可选：仅返回指定类型的文字资产",
                "items": {
                    "type": "string",
                    "enum": ["character", "scene", "prop", "plot"],
                },
            },
            "include_content": {
                "type": "boolean",
                "description": "是否返回完整 content（默认 true）；false 时仅摘要预览以节省 token",
                "default": True,
            },
        },
        required=["observation"],
        description="列出剧本相关文字资产及 content JSON",
        additional_properties=False,
    )


def build_list_project_shared_assets_input_schema() -> dict[str, Any]:
    """list_project_shared_assets：项目共享池 character/scene/prop。"""
    return _object_schema(
        {
            "observation": _OBSERVATION,
            "query": {
                "type": "string",
                "description": (
                    "可选：按名称或设定关键词检索共享池。"
                    "有 Embedding 时语义排序；无 Embedding 时名称精确/包含匹配，无命中则回退全量"
                ),
            },
            "types": {
                "type": "array",
                "description": "可选：仅返回指定共享类型（默认 character/scene/prop）",
                "items": {
                    "type": "string",
                    "enum": ["character", "scene", "prop"],
                },
            },
            "include_content": {
                "type": "boolean",
                "description": "是否返回完整 content（默认 true）；false 时仅摘要预览以节省 token",
                "default": True,
            },
        },
        required=["observation"],
        description="列出或检索项目共享图文资产（角色/空镜/道具），含是否已关联当前剧本",
        additional_properties=False,
    )


def _shot_element_refs_schema() -> dict[str, Any]:
    """子镜元素引用 schema（桶与资产类型一一对应）。"""
    return {
        "type": "object",
        "description": "子镜引用的元素文字资产 ID；各键仅允许同类型资产",
        "properties": {
            "scene": {"type": "array", "items": {"type": "string"}},
            "character": {"type": "array", "items": {"type": "string"}},
            "prop": {"type": "array", "items": {"type": "string"}},
            "frame": {"type": "array", "items": {"type": "string"}},
        },
    }


def build_sub_shot_image_schema() -> dict[str, Any]:
    """子镜关联图片 schema。"""
    return _object_schema(
        {
            "kind": {
                "type": "string",
                "enum": ["static", "video"],
                "description": "static=静态图；video=图生/文生视频意图",
            },
            "start_ms": {
                "type": "integer",
                "description": "该画面占用时段起点，相对镜起点毫秒；省略则等于所属子镜 start_ms",
            },
            "end_ms": {
                "type": "integer",
                "description": "该画面占用时段终点，相对镜起点毫秒；省略则等于所属子镜 end_ms",
            },
            "video_prompt": {"type": "string", "description": "视频生成提示（可选）"},
        },
        required=["kind"],
    )


def build_sub_shot_video_schema() -> dict[str, Any]:
    """子镜关联视频 schema。"""
    return _object_schema(
        {
            "start_ms": {"type": "integer", "description": "相对子镜起点毫秒"},
            "end_ms": {"type": "integer", "description": "相对子镜起点毫秒"},
            "source_kind": {
                "type": "string",
                "enum": ["video", "still"],
                "description": "video=视频片段；still=静图时段",
            },
        },
        required=["start_ms", "end_ms", "source_kind"],
    )


def build_sub_shot_schema() -> dict[str, Any]:
    """子镜 schema：镜内剧本时间轴时段 + 可选 images/videos。"""
    from core.edit.edit_capabilities import canonical_motions

    motions = sorted(canonical_motions())
    return _object_schema(
        {
            "id": {"type": "string", "description": "子镜 ID（create_shots 可省略，系统生成）"},
            "start_ms": {"type": "integer", "description": "相对镜起点毫秒"},
            "end_ms": {"type": "integer", "description": "相对镜起点毫秒"},
            "description": {"type": "string", "description": "子镜描述：该时段显示的内容"},
            "produce_mode": {
                "type": "string",
                "enum": ["still", "text2video", "img2video"],
                "description": "产出意图：still=静图视频；text2video=文生视频；img2video=图生视频",
            },
            "produce_rationale": {
                "type": "string",
                "description": "可选短理由（依据画面描述与时段）",
            },
            "element_refs": _shot_element_refs_schema(),
            "camera_motion": {
                "type": "string",
                "enum": motions,
                "description": "运镜 canonical preset（勿用别名）",
            },
            "images": {
                "type": "array",
                "items": build_sub_shot_image_schema(),
                "description": "关联画面图片意图（create_frames 后回填 frame_asset_id）",
            },
            "videos": {
                "type": "array",
                "items": build_sub_shot_video_schema(),
                "description": "关联视频片段（media_id 由 video_agent 回填）",
            },
        },
        required=["start_ms", "end_ms", "description"],
    )


def build_shot_visual_schema() -> dict[str, Any]:
    """兼容别名：返回子镜 schema。"""
    return build_sub_shot_schema()


def build_shot_audio_track_schema(*, require_voice_text: bool = False) -> dict[str, Any]:
    """音频轨 schema：voice（角色音）/ background（背景音）。"""
    clip_required = ["start_ms", "end_ms"]
    if require_voice_text:
        clip_required = ["start_ms", "end_ms", "text"]
    clip = _object_schema(
        {
            "start_ms": {"type": "integer", "description": "相对镜起点毫秒"},
            "end_ms": {"type": "integer"},
            "text": {
                "type": "string",
                "description": (
                    "该 clip 的朗读文案（voice 轨必填）；"
                    "仅写当前说话人的台词，勿在同条内混写旁白与多角色对白"
                ),
            },
            "character_ref": {
                "type": "string",
                "description": (
                    "说话人：角色对白填 load_context.characters[].id（txt_*）；"
                    "旁白/画外音/场景叙述留空。须与 voice_speakers 列表一致"
                ),
            },
            "voice": {"type": "string", "description": "音色（可选）"},
        },
        required=clip_required,
    )
    return _object_schema(
        {
            "kind": {"type": "string", "enum": ["voice", "background"]},
            "name": {"type": "string"},
            "clips": {"type": "array", "items": clip, "minItems": 1},
        },
        required=["kind", "clips"],
    )


def build_shot_audio_track_schema_legacy() -> dict[str, Any]:
    """兼容入口：不要求 voice clip text。"""
    return build_shot_audio_track_schema(require_voice_text=False)


def build_shot_subtitle_schema() -> dict[str, Any]:
    """字幕 schema。"""
    return _object_schema(
        {
            "text": {"type": "string"},
            "start_ms": {"type": "integer", "description": "相对镜起点毫秒"},
            "end_ms": {"type": "integer"},
        },
        required=["text", "start_ms", "end_ms"],
    )


def build_shot_schema(*, require_voice: bool = False) -> dict[str, Any]:
    """分镜（镜内多轨）schema：子镜轨 + 音频轨 + 字幕。视频轨由系统按子镜派生。"""
    required = ["order", "duration_ms", "sub_shots"]
    if require_voice:
        required.append("audio_tracks")
    return _object_schema(
        {
            "order": {"type": "integer", "description": "镜头序号（从 0 起）"},
            "duration_ms": {
                "type": "integer",
                "description": "整镜时长（毫秒，无硬上限）；须容纳镜内所有片段终点，通常由配音/素材实测驱动",
            },
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "sub_shots": {
                "type": "array",
                "items": build_sub_shot_schema(),
                "description": "子镜轨：镜内剧本时间轴各时段（至少一个，时段须落在 duration_ms 内）",
                "minItems": 1,
            },
            "audio_tracks": {
                "type": "array",
                "items": build_shot_audio_track_schema(require_voice_text=False),
                "description": "音频轨：角色音(voice)/背景音(background)，可多条；图文管线每镜至少 1 条 voice",
                **({"minItems": 1} if require_voice else {}),
            },
            "subtitles": {
                "type": "array",
                "items": build_shot_subtitle_schema(),
                "description": "镜内字幕（相对镜起点）",
            },
        },
        required=required,
        additional_properties=True,
    )


def _collect_dangling_def_refs(schema: dict[str, Any]) -> list[str]:
    """递归收集指向 #/$defs/ 但根 schema 无 $defs 的悬空 $ref。"""
    dangling: list[str] = []
    root_defs = schema.get("$defs")

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                def_name = ref.split("/")[-1]
                if not isinstance(root_defs, dict) or def_name not in root_defs:
                    dangling.append(ref)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema)
    return dangling


def build_video_plan_shot_schema() -> dict[str, Any]:
    """兼容入口：返回镜内多轨 Shot schema。"""
    return build_shot_schema()


def build_shots_array_schema(*, require_voice: bool = False) -> dict[str, Any]:
    """镜头列表 schema；require_voice 为真时强制每镜含 voice audio_tracks 与非空 clip.text。"""
    return {
        "type": "array",
        "description": "镜头列表（镜内多轨 Shot：子镜轨 + 音频轨 + 字幕）",
        "items": build_shot_schema(require_voice=require_voice),
        "minItems": 1,
    }


def build_frame_item_schema() -> dict[str, Any]:
    """单条 frame 创建项 schema；sub_shot_id 全局唯一即可定位，shot_id/order 可选。"""
    return _object_schema(
        {
            "shot_id": {
                "type": "string",
                "description": "关联 Shot.id（可选；缺省时系统按 sub_shot_id 全局反查）",
            },
            "order": {
                "type": "integer",
                "description": "镜头序号（可选；shot_id 缺失时用于定位镜头）",
            },
            "sub_shot_id": {
                "type": "string",
                "description": (
                    "子镜 ShotSubShot.id（必填优先）；须使用 create_shots/get_plan 返回 JSON 中的值，"
                    "禁止自造 ID（如 shot_0_sub_0）；全局唯一，可单独定位父镜"
                ),
            },
            "sub_shot_index": {
                "type": "integer",
                "description": "镜内子镜下标（0 起）；sub_shot_id 未知时与 order 联用",
            },
            "name": {"type": "string", "description": "剧本画面资产名称"},
            "summary": {"type": "string", "description": "一句话摘要"},
            "image_prompt": {
                "type": "string",
                "description": "生图提示词（≥40 字；缺省时可用子镜 description 种子化）",
            },
            "notes": {
                "type": "string",
                "description": "AI 编排自用备注，不进入生图提示词",
            },
            "element_refs": _shot_element_refs_schema(),
            "reference_order": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["scene", "character", "prop", "frame"],
                },
                "description": "多参考图顺序，默认 scene→character→prop→frame",
            },
        },
        required=["sub_shot_id", "image_prompt", "element_refs"],
        additional_properties=True,
    )


def build_frames_array_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "description": (
            "为每个子镜创建剧本画面 frame 文字资产（frames 数量应等于计划稿子镜总数），"
            "回填 sub_shots[].images[].frame_asset_id"
        ),
        "items": build_frame_item_schema(),
    }


def build_video_clip_item_schema() -> dict[str, Any]:
    """单条 video_clip 创建项 schema；sub_shot_id 可全局定位；可传 source_frame_asset_id。"""
    return _object_schema(
        {
            "shot_id": {
                "type": "string",
                "description": "关联 Shot.id（可选；缺省时系统按 sub_shot_id 全局反查）",
            },
            "order": {
                "type": "integer",
                "description": "镜头序号（可选；shot_id 缺失时用于定位镜头）",
            },
            "sub_shot_id": {
                "type": "string",
                "description": (
                    "子镜 ShotSubShot.id（必填优先）；须使用 create_shots/get_plan 返回 JSON 中的值，"
                    "禁止自造 ID（如 shot_0_sub_0）；全局唯一，可单独定位父镜"
                ),
            },
            "sub_shot_index": {
                "type": "integer",
                "description": "镜内子镜下标（0 起）；sub_shot_id 未知时与 order 联用",
            },
            "name": {"type": "string", "description": "video_clip 文字资产名称"},
            "summary": {"type": "string", "description": "片段简述"},
            "video_prompt": {
                "type": "string",
                "description": "生视频提示词（≥40 字；缺省时可用子镜 description 种子化）",
            },
            "notes": {
                "type": "string",
                "description": "AI 编排自用备注，不进入生视频提示词",
            },
            "source_frame_asset_id": {
                "type": "string",
                "description": (
                    "图生视频源 frame 文字资产 id；frame_i2v 建议填写。"
                    "缺省时系统自动取同子镜已关联的 frame_asset_id"
                ),
            },
            "element_refs": _video_clip_element_refs_schema(),
        },
        required=["sub_shot_id", "video_prompt", "element_refs"],
        additional_properties=True,
    )


def build_video_clips_array_schema() -> dict[str, Any]:
    """video_clip 列表 schema。"""
    return {
        "type": "array",
        "description": (
            "为每个子镜创建 video_clip 文字资产（video_clips 数量应等于计划稿子镜总数），"
            "回填 sub_shots[].videos[].video_clip_asset_id；"
            "element_refs 仅 {\"frame\":[...]}（禁止 character/scene/prop）"
        ),
        "items": build_video_clip_item_schema(),
    }


def build_ask_user_question_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "observation": _OBSERVATION,
            "title": {
                "type": "string",
                "description": "弹窗标题",
            },
            "description": {
                "type": "string",
                "description": "弹窗说明（可选）",
            },
            "kind": {
                "type": "string",
                "enum": ["generic", "plan_approval"],
                "description": (
                    "确认类型：generic=一般提问；plan_approval=计划/重规划确认"
                ),
            },
            "questions": {
                "type": "array",
                "description": "向用户展示的问题列表",
                "items": _object_schema(
                    {
                        "id": {"type": "string", "description": "字段 ID，用于回传 values"},
                        "prompt": {"type": "string", "description": "问题标签/提示"},
                        "component": {
                            "type": "string",
                            "enum": ["text", "select", "checkbox"],
                            "description": "表单组件类型",
                        },
                        "options": {
                            "type": "array",
                            "description": "select 选项",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "value": {"type": "string"},
                                },
                            },
                        },
                        "required": {"type": "boolean"},
                        "default": {"description": "默认值"},
                    },
                    required=["id", "prompt"],
                    additional_properties=True,
                ),
            },
        },
        required=["observation", "questions"],
        additional_properties=True,
    )
