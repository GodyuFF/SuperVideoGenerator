"""从领域模型构建 action input_schema。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from core.models.image_text_asset import (
    CharacterContent,
    CharacterTraits,
    PropContent,
    PropTraits,
    SceneContent,
    SceneTraits,
)
from core.models.entities import VideoPlanShot

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


def build_video_plan_shot_schema() -> dict[str, Any]:
    from core.edit.edit_capabilities import known_motions

    props = dict(_model_properties(VideoPlanShot))
    motions = sorted(known_motions())
    if "camera_motion" in props:
        cam = dict(props.get("camera_motion") or {})
        cam["type"] = "string"
        cam["enum"] = motions
        cam["description"] = (
            "运镜 preset（须为 edit_capabilities 枚举或别名；"
            "禁止自造 gentle_* / slow_* / push_* 等名称）"
        )
        props["camera_motion"] = cam
    return _object_schema(props, additional_properties=True)


def build_shots_array_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "description": "镜头列表，对齐 VideoPlanShot",
        "items": build_video_plan_shot_schema(),
    }


def build_frame_item_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "shot_id": {"type": "string", "description": "关联 VideoPlanShot.id"},
            "order": {"type": "integer", "description": "镜头序号（shot_id 缺失时备用）"},
            "name": {"type": "string", "description": "画面资产名称"},
            "summary": {"type": "string"},
            "description": {"type": "string", "description": "画面构图与叙事说明"},
            "composition_prompt": {"type": "string", "description": "图生图合成补充指令"},
            "element_refs": {
                "type": "object",
                "description": "引用元素文字资产 ID",
                "properties": {
                    "scene": {"type": "array", "items": {"type": "string"}},
                    "character": {"type": "array", "items": {"type": "string"}},
                    "prop": {"type": "array", "items": {"type": "string"}},
                },
            },
            "variant_refs": {
                "type": "object",
                "description": "text_asset_id → variant_id",
                "additionalProperties": {"type": "string"},
            },
            "reference_order": {
                "type": "array",
                "items": {"type": "string", "enum": ["scene", "character", "prop"]},
                "description": "多参考图顺序，默认 scene→character→prop",
            },
        },
        required=["description", "element_refs"],
        additional_properties=True,
    )


def build_frames_array_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "description": "每镜头 1 个画面（frame）资产，element_refs 指向空镜/角色/物品",
        "items": build_frame_item_schema(),
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
