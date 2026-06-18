"""对话会话：绑定 conversation_id 与剧本/项目。"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from core.llm.react_session import new_conversation_id


@dataclass
class DialogueSession:
    conversation_id: str
    project_id: str
    script_id: str
    user_message: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class DialogueSessionStore:
    """内存对话会话索引（conversation_id → 会话元数据）。"""

    def __init__(self) -> None:
        self._by_id: dict[str, DialogueSession] = {}
        self._by_script: dict[str, list[str]] = {}

    def create(
        self,
        project_id: str,
        script_id: str,
        user_message: str,
        conversation_id: str | None = None,
    ) -> str:
        cid = conversation_id or new_conversation_id()
        session = DialogueSession(
            conversation_id=cid,
            project_id=project_id,
            script_id=script_id,
            user_message=user_message,
        )
        self._by_id[cid] = session
        self._by_script.setdefault(script_id, []).append(cid)
        return cid
