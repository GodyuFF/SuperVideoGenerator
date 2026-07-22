"""Skill references 渐进加载：list_skill_refs / read_skill_ref。"""

from __future__ import annotations

from typing import Any

from core.llm.agent.react_core import AgentRunContext
from core.llm.prompt.skills.loader import REF_BODY_MAX_CHARS, list_skill_ref_entries, read_skill_ref_body
from core.llm.prompt.tools.schema_builders import _OBSERVATION, _object_schema
from core.llm.tools.result import ToolResult
from core.llm.tools.spec import ToolKind, ToolSpec
from core.llm.tools.validators import validate_against_schema
from core.store.memory import MemoryStore

LIST_SKILL_REFS = "list_skill_refs"
READ_SKILL_REF = "read_skill_ref"
COMMON_AGENT = "common"
SKILL_ONLY_COMMON_TOOLS = frozenset({LIST_SKILL_REFS, READ_SKILL_REF})


def list_skill_refs_input_schema() -> dict[str, Any]:
    """list_skill_refs 输入 schema。"""
    return _object_schema(
        {
            "observation": _OBSERVATION,
            "note": {"type": "string", "description": "可选说明"},
        },
        required=["observation"],
        description="列出当前激活 Skill 的 references 索引",
        additional_properties=True,
    )


def read_skill_ref_input_schema() -> dict[str, Any]:
    """read_skill_ref 输入 schema。"""
    return _object_schema(
        {
            "observation": _OBSERVATION,
            "ref_id": {
                "type": "string",
                "description": "参考文档 id（见 list_skill_refs / 索引）",
            },
            "max_chars": {
                "type": "integer",
                "description": f"正文最大字符数（默认 {REF_BODY_MAX_CHARS}）",
                "minimum": 500,
                "maximum": 50000,
            },
            "note": {"type": "string", "description": "可选说明"},
        },
        required=["observation", "ref_id"],
        description="按需读取 Skill references 正文",
        additional_properties=True,
    )


def list_skill_refs_output_schema() -> dict[str, Any]:
    """list_skill_refs 输出 schema。"""
    return _object_schema(
        {
            "skill_id": {"type": "string"},
            "refs": {"type": "array"},
            "valid": {"type": "boolean"},
        },
        required=["skill_id", "refs", "valid"],
        additional_properties=True,
    )


def read_skill_ref_output_schema() -> dict[str, Any]:
    """read_skill_ref 输出 schema。"""
    return _object_schema(
        {
            "skill_id": {"type": "string"},
            "ref_id": {"type": "string"},
            "title": {"type": "string"},
            "content": {"type": "string"},
            "truncated": {"type": "boolean"},
            "content_length": {"type": "integer"},
            "valid": {"type": "boolean"},
        },
        required=["ref_id", "content", "truncated", "valid"],
        additional_properties=True,
    )


def _active_skill_id(ctx: AgentRunContext) -> str:
    """从 work_context.skill_overlay 取当前 Skill id。"""
    overlay = ctx.work_context.get("skill_overlay") or {}
    return str(overlay.get("id") or "").strip().lower()


def handle_list_skill_refs(
    store: MemoryStore,
    ctx: AgentRunContext,
    args: dict[str, Any],
) -> ToolResult:
    """列出当前 Skill 的 references 索引（可按本 Agent 过滤）。"""
    del store
    try:
        validate_against_schema(args, list_skill_refs_input_schema(), label="输入")
    except ValueError as e:
        return ToolResult(
            observation=str(e),
            structured={"error": str(e), "valid": False},
            ok=False,
        )
    skill_id = _active_skill_id(ctx)
    if not skill_id:
        return ToolResult(
            observation="当前未激活 Skill，无法列出 references。请先使用 /skillId 或请主编排 tool_switch_skill。",
            structured={"error": "no_active_skill", "valid": False, "refs": []},
            ok=False,
        )
    entries = list_skill_ref_entries(skill_id, agent_name=ctx.agent_name)
    lines = [f"Skill「{skill_id}」可查阅参考（{len(entries)}）："]
    refs_out: list[dict[str, Any]] = []
    for e in entries:
        refs_out.append(e.to_dict())
        agent_hint = f"（agents: {', '.join(e.agents)}）" if e.agents else ""
        lines.append(f"- {e.id}：{e.title} — {e.summary or '（无摘要）'}{agent_hint}")
    if not entries:
        lines.append("（无 references；可仅依赖 Skill 补充说明）")
    else:
        lines.append("需要正文时调用 read_skill_ref(ref_id=…)。")
    return ToolResult(
        observation="\n".join(lines),
        structured={"skill_id": skill_id, "refs": refs_out, "valid": True},
        ok=True,
    )


def handle_read_skill_ref(
    store: MemoryStore,
    ctx: AgentRunContext,
    args: dict[str, Any],
) -> ToolResult:
    """按需读取当前 Skill 的某条 reference 正文。"""
    del store
    try:
        validate_against_schema(args, read_skill_ref_input_schema(), label="输入")
    except ValueError as e:
        return ToolResult(
            observation=str(e),
            structured={"error": str(e), "valid": False},
            ok=False,
        )
    skill_id = _active_skill_id(ctx)
    if not skill_id:
        return ToolResult(
            observation="当前未激活 Skill，无法读取 reference。",
            structured={"error": "no_active_skill", "valid": False},
            ok=False,
        )
    ref_id = str(args.get("ref_id", "")).strip()
    max_chars = args.get("max_chars")
    if max_chars is not None:
        try:
            max_chars = int(max_chars)
        except (TypeError, ValueError):
            max_chars = REF_BODY_MAX_CHARS
    else:
        max_chars = REF_BODY_MAX_CHARS
    # 可见性：若索引对该 Agent 限制，拒绝读取
    visible = {e.id for e in list_skill_ref_entries(skill_id, agent_name=ctx.agent_name)}
    if ref_id not in visible:
        all_ids = {e.id for e in list_skill_ref_entries(skill_id)}
        if ref_id in all_ids:
            return ToolResult(
                observation=f"参考「{ref_id}」不适用于当前 Agent「{ctx.agent_name}」。",
                structured={
                    "error": "agent_not_allowed",
                    "ref_id": ref_id,
                    "valid": False,
                },
                ok=False,
            )
    result = read_skill_ref_body(skill_id, ref_id, max_chars=max_chars)
    if not result.get("ok"):
        err = str(result.get("error") or "读取失败")
        return ToolResult(
            observation=err,
            structured={**result, "skill_id": skill_id, "valid": False},
            ok=False,
        )
    title = result.get("title") or ref_id
    content = str(result.get("content") or "")
    truncated = bool(result.get("truncated"))
    lines = [
        f"已读取 Skill「{skill_id}」参考「{title}」（id={ref_id}）",
    ]
    if truncated:
        lines.append(f"（正文已截断，原文约 {result.get('content_length', 0)} 字）")
    lines.append("")
    lines.append(content)
    return ToolResult(
        observation="\n".join(lines),
        structured={
            "skill_id": skill_id,
            "ref_id": ref_id,
            "title": title,
            "content": content,
            "truncated": truncated,
            "content_length": int(result.get("content_length") or 0),
            "valid": True,
        },
        ok=True,
    )


def build_list_skill_refs_tool_spec() -> ToolSpec:
    """构建 list_skill_refs ToolSpec。"""
    return ToolSpec(
        name=LIST_SKILL_REFS,
        description="列出当前激活 Skill 的 references 索引（渐进加载 L3 目录）",
        agent=COMMON_AGENT,
        input_schema=list_skill_refs_input_schema(),
        output_schema=list_skill_refs_output_schema(),
        kind=ToolKind.READ,
        handler=handle_list_skill_refs,
        logical_name="common.list_skill_refs",
    )


def build_read_skill_ref_tool_spec() -> ToolSpec:
    """构建 read_skill_ref ToolSpec。"""
    return ToolSpec(
        name=READ_SKILL_REF,
        description="按 ref_id 读取当前激活 Skill 的 reference 正文（渐进加载）",
        agent=COMMON_AGENT,
        input_schema=read_skill_ref_input_schema(),
        output_schema=read_skill_ref_output_schema(),
        kind=ToolKind.READ,
        handler=handle_read_skill_ref,
        logical_name="common.read_skill_ref",
    )
