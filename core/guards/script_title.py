"""剧本标题稳定性：确认后的标题不被对话摘要或 LLM 随意覆盖。"""

from __future__ import annotations

# 创建时占位 / 系统默认名，允许被剧本设计结果或用户手动改名替换
_PLACEHOLDER_TITLES = frozenset(
    {
        "",
        "默认剧本",
        "未命名剧本",
        "新剧本",
        "新对话",
    }
)


def is_mutable_script_title(title: str | None) -> bool:
    """
    当前标题是否仍可被系统/Agent 写入。

    占位名、空标题，或由用户消息截断预览污染的标题（以 … 结尾且较短）可替换；
    已确认的正式标题不可被对话或 Agent 随意改写。
    """
    text = (title or "").strip()
    if text in _PLACEHOLDER_TITLES:
        return True
    # 历史 bug：曾用用户消息 48 字预览覆盖剧本标题
    if text.endswith("…") and len(text) <= 49:
        return True
    return False


def apply_script_title_if_allowed(script_title: str, proposed: str | None) -> str | None:
    """
    若允许用 proposed 替换当前标题则返回规范化新标题，否则返回 None。

    用户手动 PATCH 不走此函数，始终可改。
    """
    if proposed is None:
        return None
    next_title = str(proposed).strip()
    if not next_title:
        return None
    if not is_mutable_script_title(script_title):
        return None
    return next_title
