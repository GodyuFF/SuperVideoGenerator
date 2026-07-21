"""工作台图文资产草稿生成工具（单工具、JSON 输出，不注册 Agent Registry）。"""

from __future__ import annotations

import json
from typing import Any

from core.llm.client import LLMClient
from core.llm.model.llm_request import LlmRequest
from core.llm.prompt.tools.schema_builders import (
    build_text_asset_draft_tool_input_schema,
    build_text_asset_draft_tool_output_schema,
)
from core.models.entities import TextAssetType
from core.models.image_text_asset import (
    CharacterTraits,
    PropTraits,
    SceneTraits,
    normalize_image_text_content,
)
from core.models.video_text_asset import normalize_video_clip_content
from core.store.memory import MemoryStore

TOOL_NAME = "generate_text_asset_draft"
"""工作台专用工具名；故意不调用 ToolRegistry.register。"""

WORKBENCH_AGENT = "workbench"

INPUT_SCHEMA = build_text_asset_draft_tool_input_schema()
OUTPUT_SCHEMA = build_text_asset_draft_tool_output_schema()

_TYPE_LABEL: dict[str, str] = {
    "character": "角色",
    "scene": "空镜",
    "prop": "物品",
    "frame": "画面",
    "video_clip": "视频片段",
}

_SUPPORTED = frozenset(_TYPE_LABEL)


def _script_context(store: MemoryStore, script_id: str) -> dict[str, str]:
    """读取剧本标题与正文摘要，供 LLM 理解语境。"""
    script = store.get_script(script_id)
    if not script:
        return {"title": "", "content_excerpt": ""}
    body = (script.content_md or "").strip()
    if len(body) > 3000:
        body = body[:3000] + "\n…（正文已截断）"
    return {
        "title": (script.title or "").strip(),
        "content_excerpt": body,
    }


_CONTENT_FIELD_SPECS: dict[str, tuple[str, ...]] = {
    "character": (
        "summary",
        "description",
        "prompt_hint",
        "visual_style",
        "color_palette",
        *CharacterTraits.model_fields.keys(),
    ),
    "scene": (
        "summary",
        "description",
        "prompt_hint",
        "visual_style",
        "color_palette",
        *SceneTraits.model_fields.keys(),
    ),
    "prop": (
        "summary",
        "description",
        "prompt_hint",
        "visual_style",
        "color_palette",
        *PropTraits.model_fields.keys(),
    ),
    "frame": (
        "summary",
        "image_prompt",
        "notes",
    ),
    "video_clip": (
        "summary",
        "video_prompt",
        "notes",
    ),
}


def _compact_content_field_spec(asset_type: str) -> str:
    """生成精简字段说明，避免把完整 JSON Schema 塞进 prompt 挤占输出 token。"""
    fields = _CONTENT_FIELD_SPECS.get(asset_type, ())
    lines = [f"- {key}" for key in fields]
    if asset_type == "frame":
        lines.append('- element_refs: {"scene":[],"character":[],"prop":[],"frame":[]}')
    if asset_type == "video_clip":
        lines.append('- element_refs: {"frame":[]}')
    return "\n".join(lines)


def _build_system_prompt(asset_type: str) -> str:
    """组装系统提示：约束 JSON 结构与各类型业务规则。"""
    label = _TYPE_LABEL[asset_type]
    field_spec = _compact_content_field_spec(asset_type)
    scene_rule = ""
    if asset_type == "scene":
        scene_rule = (
            "\n- 空镜仅描述无人环境背景板，禁止人物/动物/叙事动作/独立道具主体。"
        )
    frame_rule = ""
    if asset_type == "frame":
        frame_rule = (
            "\n- 画面仅五块：summary / image_prompt / notes / element_refs（及名称）；"
            "image_prompt 为面向生图的完整提示词；notes 仅供 AI 编排自用，勿写入提示词；"
            "element_refs 可留空数组。勿填 description/composition_prompt/visual_style 等旧字段。"
        )
    video_clip_rule = ""
    if asset_type == "video_clip":
        video_clip_rule = (
            "\n- 视频片段仅五块：summary / video_prompt / notes / element_refs；"
            "video_prompt 不少于 80 字；notes 仅供 AI 编排自用；"
            "element_refs 仅可填 frame 桶（`{\"frame\":[]}`），可留空数组；"
            "禁止 character/scene/prop；勿手写 prompt_locked / video_mode / camera_motion。"
        )
    if asset_type == "video_clip":
        prompt_rule = "- content.video_prompt 生视频提示词不少于 80 字。"
    elif asset_type == "frame":
        prompt_rule = "- content.image_prompt 生图提示词不少于 80 字。"
    else:
        prompt_rule = "- description 主视觉描述不少于 80 字，面向 AI 生图。"
    no_auto = (
        "- 不要填写 negative_prompt、prompt_version、prompt_locked、image_variants。"
        if asset_type in ("frame", "video_clip")
        else "- 不要填写 image_prompt、negative_prompt、prompt_version、prompt_locked、image_variants。"
    )
    return (
        f"你是 SuperVideoGenerator 工作台「{label}」图文资产草稿生成器。\n"
        "根据用户摘要、剧本上下文与已填 hints，输出严格 JSON 对象，格式为：\n"
        '{"name": "资产名称", "content": { ... }}\n'
        "规则：\n"
        f"- content 须包含以下字段（字符串，无信息填「未指定」）：\n{field_spec}\n"
        f"{prompt_rule}\n"
        f"{no_auto}"
        f"{scene_rule}{frame_rule}{video_clip_rule}\n"
        "- 最终回答必须是单个 JSON 对象（可放在正文或推理输出中），不要 markdown 代码块或额外解释。"
    )


def _build_user_message(
    *,
    asset_type: str,
    summary: str,
    name: str,
    hints: dict[str, Any] | None,
    script_ctx: dict[str, str],
) -> str:
    """组装用户消息：摘要、可选名称、hints 与剧本摘录。"""
    parts = [
        f"资产类型：{asset_type}（{_TYPE_LABEL[asset_type]}）",
        f"用户摘要：{summary.strip()}",
    ]
    if name.strip():
        parts.append(f"建议名称：{name.strip()}")
    if hints:
        parts.append(
            "用户已填写字段（请保留或在此基础上补全）：\n"
            + json.dumps(hints, ensure_ascii=False, indent=2)
        )
    if script_ctx.get("title") or script_ctx.get("content_excerpt"):
        parts.append(
            "剧本上下文：\n"
            f"标题：{script_ctx.get('title') or '（无）'}\n"
            f"正文摘录：\n{script_ctx.get('content_excerpt') or '（无）'}"
        )
    return "\n\n".join(parts)


def normalize_draft_payload(
    asset_type: str,
    raw: dict[str, Any],
    *,
    fallback_name: str = "",
) -> dict[str, Any]:
    """校验并规范化 LLM 返回的草稿 JSON。"""
    if asset_type not in _SUPPORTED:
        raise ValueError(f"不支持的资产类型: {asset_type}")
    name = str(raw.get("name", "")).strip() or fallback_name.strip()
    if not name:
        raise ValueError("生成结果缺少资产名称")
    content_raw = raw.get("content")
    if not isinstance(content_raw, dict):
        raise ValueError("生成结果缺少 content 对象")
    type_enum = TextAssetType(asset_type)
    if asset_type == "video_clip":
        content = normalize_video_clip_content(content_raw)
        if not str(content.get("video_prompt", "")).strip():
            raise ValueError("生成结果缺少 content.video_prompt")
    else:
        content = normalize_image_text_content(type_enum, content_raw)
        if asset_type == "frame":
            if not str(content.get("image_prompt", "")).strip():
                # 兼容模型仍返回 description 的情况
                legacy = str(content.get("description", "")).strip()
                if legacy:
                    content["image_prompt"] = legacy
            if not str(content.get("image_prompt", "")).strip():
                raise ValueError("生成结果缺少 content.image_prompt")
            content["prompt_locked"] = True
        elif not str(content.get("description", "")).strip():
            raise ValueError("生成结果缺少 content.description")
    if not str(content.get("summary", "")).strip():
        content["summary"] = summary_fallback(name, content, asset_type=asset_type)
    return {"name": name, "content": content}


def summary_fallback(name: str, content: dict[str, Any], *, asset_type: str = "") -> str:
    """当 LLM 未填 summary 时，用 image_prompt/video_prompt/description 首句或名称兜底。"""
    if asset_type == "video_clip":
        desc = str(content.get("video_prompt", "")).strip()
    elif asset_type == "frame":
        desc = str(content.get("image_prompt") or content.get("description") or "").strip()
    else:
        desc = str(content.get("description", "")).strip()
    if desc:
        first = desc.split("。")[0].split("\n")[0].strip()
        if first:
            return first[:120]
    return name


async def generate_text_asset_draft(
    llm_client: LLMClient,
    store: MemoryStore,
    *,
    project_id: str,
    script_id: str,
    asset_type: str,
    summary: str,
    name: str = "",
    hints: dict[str, Any] | None = None,
    log_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """调用配置 LLM 生成图文资产草稿（工作台专用，不经 Agent 工具链）。"""
    clean_type = str(asset_type).strip().lower()
    if clean_type not in _SUPPORTED:
        raise ValueError(f"不支持的资产类型: {asset_type}")
    clean_summary = summary.strip()
    if not clean_summary:
        raise ValueError("摘要不能为空")
    if not store.get_project(project_id):
        raise ValueError(f"项目 {project_id} 不存在")
    if not store.get_script(script_id):
        raise ValueError(f"剧本 {script_id} 不存在")

    script_ctx = _script_context(store, script_id)
    system = _build_system_prompt(clean_type)
    user_msg = _build_user_message(
        asset_type=clean_type,
        summary=clean_summary,
        name=name,
        hints=hints,
        script_ctx=script_ctx,
    )
    ctx = dict(log_context or {})
    ctx.setdefault("project_id", project_id)
    ctx.setdefault("script_id", script_id)
    ctx.setdefault("workbench_tool", TOOL_NAME)

    raw = await llm_client.complete_json(
        LlmRequest(
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        ),
        log_context=ctx,
        summary_prefix=f"工作台 {TOOL_NAME}",
    )
    if not isinstance(raw, dict):
        raise ValueError("LLM 返回格式无效")
    return normalize_draft_payload(
        clean_type,
        raw,
        fallback_name=name.strip() or clean_summary[:40],
    )
