"""Claude Code 风格 System Prompt Section 注册表与动态边界支持。

提供命名 Section、边界标记、DANGEROUS uncached 标记，以及 assemble_system_prompt 组装入口。
当前阶段重点是逻辑结构与可扩展性；cache_control 断点在 Client 层按需注入（Anthropic 原生或兼容层 fallback）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

# 动态边界标记（与 Claude Code __SYSTEM_PROMPT_DYNAMIC_BOUNDARY__ 对齐）
BOUNDARY_MARKER = "__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__"


@dataclass(frozen=True)
class SystemPromptSection:
    """单个 System Prompt Section。

    content: 静态字符串或 ctx -> str 的惰性函数
    cache: 是否建议在 API 层加 cache_control（ephemeral）
    dangerous_uncached: 是否每轮必须重算（对应 DANGEROUS_ 语义，需 reason）
    reason: dangerous 时的解释（审计用）
    """

    name: str
    content: str | Callable[[Any], str]
    cache: bool = True
    dangerous_uncached: bool = False
    reason: str = ""


# 按 prompt 类型（react / action / summary）注册的 section 列表
# 顺序即最终 system 块顺序；BOUNDARY_MARKER 会插入为特殊块
SECTION_REGISTRY: dict[str, list[SystemPromptSection]] = {}


def register_section(prompt_type: str, section: SystemPromptSection) -> None:
    """注册一个 section 到指定 prompt_type（react/action/summary）。"""
    SECTION_REGISTRY.setdefault(prompt_type, []).append(section)


def get_sections(prompt_type: str) -> list[SystemPromptSection]:
    """获取某 prompt_type 的 section 列表（未找到返回空）。"""
    return SECTION_REGISTRY.get(prompt_type, [])


def assemble_system_prompt(prompt_type: str, ctx: Any = None) -> list[dict[str, Any]]:
    """组装 System Prompt blocks 列表。

    返回格式：
    [
        {"type": "text", "text": "...", "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__"},
        ...
    ]

    目前 cache_control 仅在 cache=True 且非 dangerous 时添加；
    实际发送时由 client.py 决定是否透传（Anthropic 支持，OpenAI 兼容层可 join 文本）。
    """
    sections = get_sections(prompt_type)
    blocks: list[dict[str, Any]] = []

    for sec in sections:
        if sec.name == BOUNDARY_MARKER:
            blocks.append({"type": "text", "text": BOUNDARY_MARKER})
            continue

        content = sec.content(ctx) if callable(sec.content) else sec.content
        block: dict[str, Any] = {"type": "text", "text": content}

        if sec.cache and not sec.dangerous_uncached:
            block["cache_control"] = {"type": "ephemeral"}

        if sec.dangerous_uncached and sec.reason:
            block["_dangerous_reason"] = sec.reason  # 仅元数据，不进 API payload

        blocks.append(block)

    return blocks


# 便捷构造器
def make_section(
    name: str,
    content: str | Callable[[Any], str],
    *,
    cache: bool = True,
    dangerous_uncached: bool = False,
    reason: str = "",
) -> SystemPromptSection:
    return SystemPromptSection(
        name=name,
        content=content,
        cache=cache,
        dangerous_uncached=dangerous_uncached,
        reason=reason,
    )
