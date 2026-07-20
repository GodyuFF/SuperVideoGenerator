"""解析用户消息中的 /skillId 前缀。"""

from __future__ import annotations

from core.llm.prompt.skills import resolve_skill_id


def parse_skill_command(message: str) -> tuple[str | None, str]:
    """
    解析 `/skillId` 或 `/skillId 正文`。
    返回 (skill_id, 剩余用户消息)；无 slash 时 (None, 原文)。
    """
    text = message.strip()
    if not text.startswith("/"):
        return None, text
    body = text[1:].strip()
    if not body:
        return None, text
    parts = body.split(None, 1)
    token = parts[0].strip().lower()
    rest = parts[1].strip() if len(parts) > 1 else ""
    skill_id = resolve_skill_id(token)
    if skill_id is None:
        return None, text
    return skill_id, rest
