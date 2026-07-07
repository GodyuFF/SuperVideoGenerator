"""EditTimeline clip / tracks JSON Schema（editing_agent plan_edit_timeline）。"""

from __future__ import annotations

from typing import Any

from core.edit.edit_capabilities import load_edit_capability_defs

_caps = load_edit_capability_defs()
_MOTION_ENUM = list(_caps.get("motions") or []) + list((_caps.get("motion_aliases") or {}).keys())
_TRANSITION_ENUM = list(_caps.get("transitions") or ["cut", "fade", "dissolve"])
_BACKGROUND_ENUM = list(_caps.get("backgrounds") or ["solid", "image", "blur"])
_MAX_TRANSITION_MS = int(_caps.get("transition_max_duration_ms") or 2000)

_FOCAL_PAIR = {
    "type": "array",
    "items": {"type": "number"},
    "minItems": 2,
    "maxItems": 2,
}

EDIT_CLIP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "track": {"type": "string", "enum": ["video", "audio", "subtitle"]},
        "start_ms": {"type": "integer"},
        "end_ms": {"type": "integer"},
        "label": {"type": "string"},
        "asset_ref": {"type": "string", "description": "已有 media 资产 ID（优先）"},
        "motion": {
            "type": "string",
            "enum": _MOTION_ENUM,
            "description": "运镜 preset（见 edit_capabilities.md）",
        },
        "edit_description": {
            "type": "string",
            "description": "该时间段剪辑意图详述（运镜、转场、背景、素材来源）",
        },
        "transition_in": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": _TRANSITION_ENUM},
                "duration_ms": {
                    "type": "integer",
                    "maximum": _MAX_TRANSITION_MS,
                },
            },
        },
        "transition_out": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": _TRANSITION_ENUM},
                "duration_ms": {
                    "type": "integer",
                    "maximum": _MAX_TRANSITION_MS,
                },
            },
        },
        "background": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": _BACKGROUND_ENUM},
                "color": {"type": "string"},
                "asset_ref": {"type": "string"},
            },
        },
        "motion_detail": {
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "from_focal": _FOCAL_PAIR,
                "to_focal": _FOCAL_PAIR,
                "scale_from": {"type": "number"},
                "scale_to": {"type": "number"},
            },
        },
        "source_refs": {
            "type": "object",
            "properties": {
                "shot_id": {"type": "string"},
                "text_asset_ids": {"type": "array", "items": {"type": "string"}},
                "media_ids": {"type": "array", "items": {"type": "string"}},
                "variant_ids": {"type": "array", "items": {"type": "string"}},
                "video_plan_shot_order": {"type": "integer"},
            },
        },
        "metadata": {"type": "object"},
        "layer_id": {"type": "string"},
        "transform": {
            "type": "object",
            "description": "画布变换：width/height 控制缩放（1.0=全屏，0.3=画中画）；与 motion_detail 运镜缩放叠加",
            "properties": {
                "x": {"type": "number", "minimum": 0, "maximum": 1, "description": "中心点 X，0-1"},
                "y": {"type": "number", "minimum": 0, "maximum": 1, "description": "中心点 Y，0-1"},
                "width": {
                    "type": "number",
                    "minimum": 0.05,
                    "maximum": 1,
                    "description": "宽度 0-1（全屏 1.0，画中画约 0.25-0.4）",
                },
                "height": {
                    "type": "number",
                    "minimum": 0.05,
                    "maximum": 1,
                    "description": "高度 0-1",
                },
                "opacity": {"type": "number"},
                "rotation": {"type": "number"},
                "keyframes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "time_ms": {"type": "integer"},
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "width": {"type": "number"},
                            "height": {"type": "number"},
                            "scale": {"type": "number"},
                            "opacity": {"type": "number"},
                            "rotation": {"type": "number"},
                        },
                    },
                },
            },
        },
    },
}

EDIT_VIDEO_LAYER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "z_index": {"type": "integer"},
        "clips": {"type": "array", "items": EDIT_CLIP_SCHEMA},
    },
}

EDIT_TIMELINE_TRACKS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "video": {"type": "array", "items": EDIT_CLIP_SCHEMA},
        "audio": {"type": "array", "items": EDIT_CLIP_SCHEMA},
        "subtitle": {"type": "array", "items": EDIT_CLIP_SCHEMA},
    },
}

EDIT_VIDEO_LAYERS_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": EDIT_VIDEO_LAYER_SCHEMA,
    "description": "多视频图层（z_index 越大越靠前）；主画面 z_index=0",
}
