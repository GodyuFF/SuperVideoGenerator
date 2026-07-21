"""storyboard_refine_agent 相关 action input schema。"""



from __future__ import annotations



from typing import Any



from core.llm.prompt.tools.schema_builders import _OBSERVATION, build_sub_shot_schema

from core.llm.tools.shared.input_common import (

    OBSERVATION_ONLY,

    READ_ONLY_QUERY_SCHEMA,

    merge_plan_tracking,

)



SHOT_DETAIL_PATCH_SCHEMA: dict[str, Any] = {

    "type": "object",

    "properties": {

        "shot_id": {"type": "string", "description": "Shot.id"},

        "display_instructions": {

            "type": "string",

            "description": "复核展示说明：焦点、字幕区、运镜节奏（写入镜头 review_note）",

        },

        "camera_motion_refined": {

            "type": "string",

            "description": "复核后修正运镜，覆盖首个子镜 camera_motion",

        },

        "need_regen": {

            "type": "boolean",

            "description": "构图/素材变化较大时建议重生产",

        },

        "regen_reason": {
            "type": "string",
            "description": "重生产原因（可为 JSON 结构化音画偏差说明）",
        },
        "sync_policy": {
            "type": "string",
            "enum": ["narration_master", "visual_master", "balanced"],
            "description": "音画主轨：旁白驱动 / 画面驱动 / 双向微调",
        },
        "lip_sync_required": {
            "type": "boolean",
            "description": "是否要求口型同步（强制 visual_master）",
        },
        "sync_notes": {
            "type": "string",
            "description": "音画协调备注",
        },
        "proposed_sync_actions": {
            "type": "array",
            "description": "Tier2 可选音画协调方案",
            "items": {"type": "object"},
        },

    },

    "required": ["shot_id"],

    "additionalProperties": True,

}



SUB_SHOT_TIMING_PATCH_SCHEMA: dict[str, Any] = {

    "type": "object",

    "properties": {

        "id": {"type": "string", "description": "已有子镜 ID（必填，用于增量 patch）"},

        "start_ms": {"type": "integer", "description": "相对镜起点毫秒"},

        "end_ms": {"type": "integer", "description": "相对镜起点毫秒"},

        "camera_motion": {

            "type": "string",

            "description": "运镜 canonical preset（可选，覆盖该子镜）",

        },

    },

    "required": ["id"],

    "additionalProperties": False,

}



AUDIO_CLIP_TIMING_PATCH_SCHEMA: dict[str, Any] = {

    "type": "object",

    "properties": {

        "id": {"type": "string", "description": "已有 audio clip ID"},

        "start_ms": {"type": "integer"},

        "end_ms": {"type": "integer"},

        "text": {"type": "string"},

        "media_id": {"type": "string"},

    },

    "required": ["id"],

    "additionalProperties": True,

}



SUBTITLE_TIMING_PATCH_SCHEMA: dict[str, Any] = {

    "type": "object",

    "properties": {

        "id": {"type": "string", "description": "已有字幕 ID"},

        "start_ms": {"type": "integer"},

        "end_ms": {"type": "integer"},

        "text": {"type": "string"},

    },

    "required": ["id"],

    "additionalProperties": False,

}



REVIEW_SHOT_PATCH_SCHEMA: dict[str, Any] = {

    "type": "object",

    "properties": {

        "display_instructions": SHOT_DETAIL_PATCH_SCHEMA["properties"]["display_instructions"],

        "camera_motion_refined": SHOT_DETAIL_PATCH_SCHEMA["properties"]["camera_motion_refined"],

        "need_regen": SHOT_DETAIL_PATCH_SCHEMA["properties"]["need_regen"],

        "regen_reason": SHOT_DETAIL_PATCH_SCHEMA["properties"]["regen_reason"],

        "sync_policy": SHOT_DETAIL_PATCH_SCHEMA["properties"]["sync_policy"],

        "lip_sync_required": SHOT_DETAIL_PATCH_SCHEMA["properties"]["lip_sync_required"],

        "sync_notes": SHOT_DETAIL_PATCH_SCHEMA["properties"]["sync_notes"],

        "proposed_sync_actions": SHOT_DETAIL_PATCH_SCHEMA["properties"]["proposed_sync_actions"],

    },

    "additionalProperties": True,

}



REVIEW_SHOT_RESTRUCTURE_OP_SCHEMA: dict[str, Any] = {

    "type": "object",

    "properties": {

        "op": {

            "type": "string",

            "enum": ["adjust", "split", "regen", "delete"],

            "description": "单镜结构操作；跨镜 merge/reorder/add 请用 review_and_restructure",

        },

        "duration_ms": {"type": "integer"},

        "sub_shots": {

            "type": "array",

            "items": SUB_SHOT_TIMING_PATCH_SCHEMA,

            "description": "adjust 时按 id 增量 patch 子镜时段（勿重复 description/images）",

        },

        "audio_tracks": {

            "type": "array",

            "items": {

                "type": "object",

                "properties": {

                    "id": {"type": "string", "description": "已有音轨 ID"},

                    "clips": {

                        "type": "array",

                        "items": AUDIO_CLIP_TIMING_PATCH_SCHEMA,

                    },

                },

                "required": ["id"],

            },

        },

        "subtitles": {

            "type": "array",

            "items": SUBTITLE_TIMING_PATCH_SCHEMA,

        },

        "new_shots": {

            "type": "array",

            "description": "split 时的新镜头列表（至少 2 项）",

            "items": {"type": "object"},

            "minItems": 2,

        },

        "regen_reason": {"type": "string"},

    },

    "required": ["op"],

    "additionalProperties": True,

}



REVIEW_SHOT_SCHEMA: dict[str, Any] = merge_plan_tracking(

    {

        "type": "object",

        "properties": {

            "observation": _OBSERVATION,

            "shot_id": {"type": "string", "description": "目标镜头 ID（单镜复核）"},

            "patch": REVIEW_SHOT_PATCH_SCHEMA,

            "restructure_op": REVIEW_SHOT_RESTRUCTURE_OP_SCHEMA,

        },

        "required": ["observation", "shot_id"],

        "anyOf": [

            {"required": ["patch"]},

            {"required": ["restructure_op"]},

        ],

        "additionalProperties": True,

    }

)



RESTRUCTURE_OP_SCHEMA: dict[str, Any] = {

    "type": "object",

    "properties": {

        "op": {

            "type": "string",

            "enum": ["adjust", "split", "merge", "add", "delete", "regen", "reorder"],

        },

        "shot_id": {"type": "string", "description": "adjust/split/delete/regen 目标镜头 ID"},

        "shot_ids": {

            "type": "array",

            "items": {"type": "string"},

            "minItems": 2,

            "description": "merge 时至少 2 个 shot_id",

        },

        "ordered_shot_ids": {

            "type": "array",

            "items": {"type": "string"},

            "description": "reorder 时的完整镜头 ID 新顺序",

        },

        "title": {"type": "string"},

        "summary": {"type": "string"},

        "duration_ms": {"type": "integer"},

        "review_note": {"type": "string"},

        "sub_shots": {
            "type": "array",
            "items": build_sub_shot_schema(),
            "description": "adjust 时整体替换子镜轨",
        },

        "audio_tracks": {"type": "array", "items": {"type": "object"}},

        "subtitles": {"type": "array", "items": {"type": "object"}},

        "new_shots": {

            "type": "array",

            "description": "split 时的新镜头列表（至少 2 项）",

            "items": {"type": "object"},

            "minItems": 2,

        },

        "merged_shot": {"type": "object", "description": "merge 后的合并镜头"},

        "new_shot": {"type": "object", "description": "add 时的新镜头"},

        "after_order": {"type": "integer"},

        "display_instructions": {"type": "string"},

        "regen_reason": {"type": "string"},

    },

    "required": ["op"],

    "additionalProperties": True,

}



REVIEW_RESTRUCTURE_SCHEMA: dict[str, Any] = merge_plan_tracking(

    {

        "type": "object",

        "properties": {

            "observation": _OBSERVATION,

            "restructure_ops": {

                "type": "array",

                "items": RESTRUCTURE_OP_SCHEMA,

            },

            "patches": {

                "type": "array",

                "items": SHOT_DETAIL_PATCH_SCHEMA,

            },

        },

        "required": ["observation"],

        "anyOf": [

            {"required": ["patches"], "properties": {"patches": {"minItems": 1}}},

            {

                "required": ["restructure_ops"],

                "properties": {"restructure_ops": {"minItems": 1}},

            },

        ],

        "additionalProperties": True,

    }

)



_SHOT_FILTER_PROPERTIES: dict[str, Any] = {

    "shot_id": {"type": "string", "description": "可选，单镜过滤"},

    "shot_ids": {

        "type": "array",

        "items": {"type": "string"},

        "description": "可选，多镜过滤",

    },

}



GET_SHOT_DETAILS_SCHEMA: dict[str, Any] = merge_plan_tracking(

    {

        "type": "object",

        "properties": {

            "observation": _OBSERVATION,

            **_SHOT_FILTER_PROPERTIES,

        },

        "required": ["observation"],

        "additionalProperties": True,

    }

)



GET_SHOT_ASSET_TIMING_SCHEMA: dict[str, Any] = merge_plan_tracking(

    {

        "type": "object",

        "properties": {

            "observation": _OBSERVATION,

            **_SHOT_FILTER_PROPERTIES,

            "asset_kind": {

                "type": "string",

                "enum": ["audio", "video", "all"],

                "description": "查询音频、视频或全部资产时长",

            },

        },

        "required": ["observation"],

        "additionalProperties": True,

    }

)



SYNC_SCHEMA: dict[str, Any] = merge_plan_tracking(dict(OBSERVATION_ONLY))

CHECK_PREREQUISITES_SCHEMA: dict[str, Any] = merge_plan_tracking(dict(OBSERVATION_ONLY))

ANALYZE_AV_SYNC_SCHEMA: dict[str, Any] = merge_plan_tracking(
    {
        "type": "object",
        "properties": {
            "observation": _OBSERVATION,
            "mode": {
                "type": "string",
                "enum": ["analyze_only", "hybrid", "auto_only"],
                "description": "analyze_only 只分析；hybrid 小偏差自动修；auto_only 仅自动",
            },
            "shot_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可选：仅分析指定镜头",
            },
        },
        "required": ["observation"],
        "additionalProperties": True,
    }
)

PERSIST_DETAIL_SCHEMA: dict[str, Any] = merge_plan_tracking(dict(OBSERVATION_ONLY))

UPDATE_FRAMES_SCHEMA: dict[str, Any] = merge_plan_tracking(dict(OBSERVATION_ONLY))



STORYBOARD_REFINE_SCHEMAS: dict[str, dict[str, Any]] = {

    "check_refine_prerequisites": CHECK_PREREQUISITES_SCHEMA,

    "sync_actual_assets": SYNC_SCHEMA,

    "analyze_av_sync": ANALYZE_AV_SYNC_SCHEMA,

    "review_and_restructure": REVIEW_RESTRUCTURE_SCHEMA,

    "review_shot": REVIEW_SHOT_SCHEMA,

    "update_frames": UPDATE_FRAMES_SCHEMA,

    "persist_review": PERSIST_DETAIL_SCHEMA,

    "get_refine_plan": READ_ONLY_QUERY_SCHEMA,

    "get_shot_details": GET_SHOT_DETAILS_SCHEMA,

    "get_shot_asset_timing": GET_SHOT_ASSET_TIMING_SCHEMA,

}


