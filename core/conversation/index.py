"""对话线程元数据索引（按 project / script 列表）。"""

from datetime import datetime, timezone
from typing import Any

from core.models.entities import Conversation, ConversationStatus, new_id


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationIndex:
    """conversation_id → Conversation 元数据。"""

    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}

    @property
    def conversations(self) -> dict[str, Conversation]:
        return self._conversations

    def create(
        self,
        project_id: str,
        script_id: str,
        *,
        title: str = "",
        conversation_id: str | None = None,
    ) -> Conversation:
        now = _utc_now()
        conv = Conversation(
            id=conversation_id or new_id("conv"),
            project_id=project_id,
            script_id=script_id,
            title=title.strip() or "新对话",
            created_at=now,
            updated_at=now,
        )
        self._conversations[conv.id] = conv
        return conv

    def get(self, conversation_id: str) -> Conversation | None:
        return self._conversations.get(conversation_id)

    def require(
        self,
        conversation_id: str,
        *,
        project_id: str,
        script_id: str,
    ) -> Conversation:
        conv = self.get(conversation_id)
        if not conv:
            raise ValueError("对话不存在")
        if conv.project_id != project_id or conv.script_id != script_id:
            raise ValueError("对话与项目/剧本不匹配")
        return conv

    def list_for_project(
        self,
        project_id: str,
        *,
        script_id: str | None = None,
    ) -> list[Conversation]:
        items = [
            c
            for c in self._conversations.values()
            if c.project_id == project_id
            and (script_id is None or c.script_id == script_id)
        ]
        return sorted(items, key=lambda c: c.updated_at or c.created_at, reverse=True)

    def touch_after_message(
        self,
        conversation_id: str,
        *,
        title: str | None = None,
        last_summary: str | None = None,
    ) -> Conversation | None:
        conv = self.get(conversation_id)
        if not conv:
            return None
        conv.updated_at = _utc_now()
        if title and not conv.title.strip():
            conv.title = title[:80]
        if last_summary is not None:
            conv.last_summary = last_summary
        return conv

    def record_token_round(
        self, conversation_id: str, usage: dict[str, Any]
    ) -> Conversation | None:
        conv = self.get(conversation_id)
        if not conv:
            return None
        conv.last_round_token_usage = usage
        totals = dict(conv.total_token_usage)
        for item in usage.get("models", []):
            model = str(item.get("model", "unknown"))
            prev = int(totals.get(model, 0))
            totals[model] = prev + int(item.get("total_tokens", 0))
        totals["_all"] = int(totals.get("_all", 0)) + int(usage.get("total_tokens", 0))
        conv.total_token_usage = totals
        conv.updated_at = _utc_now()
        return conv

    def clear(self) -> None:
        self._conversations.clear()

    def load_dict(self, data: dict[str, Conversation]) -> None:
        self._conversations = dict(data)
