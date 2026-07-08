"""Agent 可控剪辑工具定义 — OpenCut 集成。

供 editing_agent 通过 MCP function calling 调用：
- get_edit_timeline  — 查询当前时间轴
- add_clip           — 添加片段
- update_clip        — 修改片段
- remove_clip        — 删除片段
- apply_effect       — 应用特效
- set_keyframe       — 设置关键帧
- export_timeline    — 导出成片
- get_export_status  — 查询导出进度
"""

from __future__ import annotations

from typing import Any

OPEN_CUT_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "get_edit_timeline": {
        "type": "object",
        "properties": {
            "observation": {
                "type": "string",
                "description": "查询结果说明",
            },
        },
        "required": ["observation"],
        "additionalProperties": True,
    },
    "add_clip": {
        "type": "object",
        "properties": {
            "observation": {
                "type": "string",
                "description": "操作说明",
            },
            "media_id": {
                "type": "string",
                "description": "媒体资产 ID",
            },
            "track": {
                "type": "string",
                "enum": ["video", "audio", "subtitle"],
                "description": "目标轨道",
            },
            "start_ms": {
                "type": "integer",
                "description": "开始时间（毫秒）",
            },
            "duration_ms": {
                "type": "integer",
                "description": "时长（毫秒），默认 3000",
            },
            "layer_id": {
                "type": "string",
                "description": "目标视频层 ID（仅 video 轨道需要）",
            },
            "label": {
                "type": "string",
                "description": "片段标签",
            },
        },
        "required": ["observation", "media_id", "track", "start_ms"],
        "additionalProperties": True,
    },
    "update_clip": {
        "type": "object",
        "properties": {
            "observation": {
                "type": "string",
                "description": "操作说明",
            },
            "clip_id": {
                "type": "string",
                "description": "目标片段 ID",
            },
            "start_ms": {
                "type": "integer",
                "description": "新的开始时间",
            },
            "end_ms": {
                "type": "integer",
                "description": "新的结束时间",
            },
            "label": {
                "type": "string",
                "description": "新的标签",
            },
            "transform": {
                "type": "object",
                "description": "画面变换 {x, y, width, height, opacity, rotation}",
            },
            "motion": {
                "type": "string",
                "description": "运镜类型",
            },
            "volume": {
                "type": "number",
                "description": "音量 0.0-1.0（仅音频轨）",
            },
            "transition_in": {
                "type": "object",
                "description": "入转场 {type, duration_ms}",
            },
            "transition_out": {
                "type": "object",
                "description": "出转场 {type, duration_ms}",
            },
        },
        "required": ["observation", "clip_id"],
        "additionalProperties": True,
    },
    "remove_clip": {
        "type": "object",
        "properties": {
            "observation": {
                "type": "string",
                "description": "操作说明",
            },
            "clip_id": {
                "type": "string",
                "description": "要删除的片段 ID",
            },
        },
        "required": ["observation", "clip_id"],
        "additionalProperties": True,
    },
    "apply_effect": {
        "type": "object",
        "properties": {
            "observation": {
                "type": "string",
                "description": "操作说明",
            },
            "clip_id": {
                "type": "string",
                "description": "目标片段 ID",
            },
            "effect_type": {
                "type": "string",
                "description": "特效类型（如 blur, brightness, fade_in）",
            },
            "params": {
                "type": "object",
                "description": "特效参数",
            },
        },
        "required": ["observation", "clip_id", "effect_type"],
        "additionalProperties": True,
    },
    "set_keyframe": {
        "type": "object",
        "properties": {
            "observation": {
                "type": "string",
                "description": "操作说明",
            },
            "clip_id": {
                "type": "string",
                "description": "目标片段 ID",
            },
            "time_ms": {
                "type": "integer",
                "description": "关键帧时间",
            },
            "properties": {
                "type": "object",
                "description": "关键帧属性 {x, y, width, height, opacity, rotation}",
            },
        },
        "required": ["observation", "clip_id", "time_ms", "properties"],
        "additionalProperties": True,
    },
    "export_timeline": {
        "type": "object",
        "properties": {
            "observation": {
                "type": "string",
                "description": "操作说明",
            },
            "skip_subtitles": {
                "type": "boolean",
                "description": "是否跳过字幕",
            },
        },
        "required": ["observation"],
        "additionalProperties": True,
    },
    "get_export_status": {
        "type": "object",
        "properties": {
            "observation": {
                "type": "string",
                "description": "操作说明",
            },
            "job_id": {
                "type": "string",
                "description": "导出任务 ID",
            },
        },
        "required": ["observation", "job_id"],
        "additionalProperties": True,
    },
}

# 流水线行动（一次性的：完成后从 available_actions 中移除）
OPEN_CUT_PIPELINE_ACTIONS = frozenset({
    "export_timeline",
})

# 只读查询
OPEN_CUT_READ_ACTIONS = frozenset({
    "get_edit_timeline",
    "get_export_status",
})

# 可在任意时刻调用的写操作
OPEN_CUT_AD_HOC_ACTIONS = frozenset({
    "add_clip",
    "update_clip",
    "remove_clip",
    "apply_effect",
    "set_keyframe",
})


def get_opencut_action_schema(action: str) -> dict[str, Any]:
    """获取 action 的 JSON Schema。"""
    return dict(OPEN_CUT_TOOL_SCHEMAS.get(action, {}))
