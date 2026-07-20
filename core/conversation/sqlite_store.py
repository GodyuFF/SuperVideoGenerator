"""对话消息与 A2UI 记录的 SQLite 归档（append-only）。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.llm.a2ui.schemas import A2UIConfirmationRequest, A2UIConfirmationResponse
from core.conversation.store import ConversationMessage, MessageKind, MessageRole, load_conversation_messages
from core.models.entities import Conversation, ConversationStatus, new_id
from core.store.project_paths import DATA_ROOT

DEFAULT_DB_PATH = DATA_ROOT / "conversations.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class A2UIRecord:
    """A2UI 确认归档记录。"""

    id: str
    conversation_id: str
    confirmation_id: str
    kind: str
    title: str
    request_json: dict[str, Any]
    response_json: dict[str, Any] | None = None
    approved: bool | None = None
    created_at: str = ""
    resolved_at: str | None = None


class ConversationSqliteStore:
    """对话消息 / 元数据 / A2UI SQLite 仓储。"""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    script_id TEXT NOT NULL,
                    title TEXT,
                    last_summary TEXT,
                    status TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    last_round_token_usage TEXT,
                    total_token_usage TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    project_id TEXT,
                    script_id TEXT,
                    channel TEXT,
                    agent_name TEXT,
                    step_id TEXT,
                    role TEXT,
                    message_kind TEXT,
                    tool_call_id TEXT,
                    content TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conv_msg_conv_time
                ON conversation_messages(conversation_id, created_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conv_msg_agent
                ON conversation_messages(conversation_id, channel, agent_name)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS a2ui_records (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    confirmation_id TEXT UNIQUE,
                    kind TEXT,
                    title TEXT,
                    request_json TEXT,
                    response_json TEXT,
                    approved INTEGER,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_a2ui_conv_time
                ON a2ui_records(conversation_id, created_at)
                """
            )
            conn.commit()

    def message_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM conversation_messages"
            ).fetchone()
        return int(row["c"]) if row else 0

    def upsert_conversation(self, conv: Conversation) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conversations (
                    id, project_id, script_id, title, last_summary, status,
                    created_at, updated_at, last_round_token_usage, total_token_usage
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    last_summary=excluded.last_summary,
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    last_round_token_usage=excluded.last_round_token_usage,
                    total_token_usage=excluded.total_token_usage
                """,
                (
                    conv.id,
                    conv.project_id,
                    conv.script_id,
                    conv.title,
                    conv.last_summary,
                    conv.status.value if isinstance(conv.status, ConversationStatus) else str(conv.status),
                    conv.created_at,
                    conv.updated_at,
                    json.dumps(conv.last_round_token_usage, ensure_ascii=False),
                    json.dumps(conv.total_token_usage, ensure_ascii=False),
                ),
            )
            conn.commit()

    def list_conversations(
        self, project_id: str, *, script_id: str | None = None
    ) -> list[Conversation]:
        clauses = ["project_id = ?"]
        params: list[Any] = [project_id]
        if script_id:
            clauses.append("script_id = ?")
            params.append(script_id)
        where = " AND ".join(clauses)
        sql = f"SELECT * FROM conversations WHERE {where} ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_conversation(r) for r in rows]

    def list_all_conversations(self) -> list[Conversation]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC"
            ).fetchall()
        return [self._row_to_conversation(r) for r in rows]

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        return self._row_to_conversation(row) if row else None

    def backfill_messages(self, messages_dict: dict[str, list[ConversationMessage]]) -> int:
        """将内存/JSON 中的消息补写入 SQLite（INSERT OR IGNORE）。"""
        imported = 0
        # 快照避免 persist_store_async 线程迭代时主线程 setdefault 新增 key
        for msgs in list(messages_dict.values()):
            for msg in list(msgs):
                self.append_message(msg)
                imported += 1
        return imported

    def append_message(self, msg: ConversationMessage) -> ConversationMessage:
        if not msg.created_at:
            msg.created_at = _utc_now()
        content_json = json.dumps(msg.content, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO conversation_messages (
                    id, conversation_id, project_id, script_id, channel,
                    agent_name, step_id, role, message_kind, tool_call_id,
                    content, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    msg.id,
                    msg.conversation_id,
                    msg.project_id,
                    msg.script_id,
                    msg.channel,
                    msg.agent_name,
                    getattr(msg, "step_id", "") or "",
                    msg.role.value if isinstance(msg.role, MessageRole) else str(msg.role),
                    msg.message_kind.value
                    if isinstance(msg.message_kind, MessageKind)
                    else str(msg.message_kind),
                    msg.tool_call_id,
                    content_json,
                    msg.created_at,
                ),
            )
            conn.commit()
        return msg

    def append_messages_batch(self, messages: list[ConversationMessage]) -> int:
        """批量插入消息（单次 connect + commit）。"""
        if not messages:
            return 0
        with self._connect() as conn:
            for msg in messages:
                if not msg.created_at:
                    msg.created_at = _utc_now()
                content_json = json.dumps(msg.content, ensure_ascii=False)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO conversation_messages (
                        id, conversation_id, project_id, script_id, channel,
                        agent_name, step_id, role, message_kind, tool_call_id,
                        content, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        msg.id,
                        msg.conversation_id,
                        msg.project_id,
                        msg.script_id,
                        msg.channel,
                        msg.agent_name,
                        getattr(msg, "step_id", "") or "",
                        msg.role.value
                        if isinstance(msg.role, MessageRole)
                        else str(msg.role),
                        msg.message_kind.value
                        if isinstance(msg.message_kind, MessageKind)
                        else str(msg.message_kind),
                        msg.tool_call_id,
                        content_json,
                        msg.created_at,
                    ),
                )
            conn.commit()
        return len(messages)

    def list_messages_page(
        self,
        conversation_id: str,
        *,
        limit: int = 80,
        before_created_at: str | None = None,
    ) -> list[ConversationMessage]:
        """按时间倒序分页拉取消息（返回升序）。"""
        clauses = ["conversation_id = ?"]
        params: list[Any] = [conversation_id]
        if before_created_at:
            clauses.append("created_at < ?")
            params.append(before_created_at)
        params.append(max(1, min(limit, 500)))
        sql = f"""
            SELECT * FROM (
                SELECT * FROM conversation_messages
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
            ) sub
            ORDER BY created_at ASC, id ASC
        """
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_message(r) for r in rows]

    def list_messages(self, conversation_id: str) -> list[ConversationMessage]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM conversation_messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (conversation_id,),
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def append_a2ui_request(
        self,
        conversation_id: str,
        request: A2UIConfirmationRequest,
    ) -> A2UIRecord:
        record = A2UIRecord(
            id=new_id("a2ui"),
            conversation_id=conversation_id,
            confirmation_id=request.confirmation_id,
            kind=str(request.kind),
            title=request.title,
            request_json=request.model_dump(),
            created_at=_utc_now(),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO a2ui_records (
                    id, conversation_id, confirmation_id, kind, title,
                    request_json, response_json, approved, created_at, resolved_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    record.id,
                    record.conversation_id,
                    record.confirmation_id,
                    record.kind,
                    record.title,
                    json.dumps(record.request_json, ensure_ascii=False),
                    None,
                    None,
                    record.created_at,
                    None,
                ),
            )
            conn.commit()
        return record

    def resolve_a2ui(
        self, response: A2UIConfirmationResponse
    ) -> A2UIRecord | None:
        resolved_at = _utc_now()
        response_json = response.model_dump()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE a2ui_records
                SET response_json = ?, approved = ?, resolved_at = ?
                WHERE confirmation_id = ?
                """,
                (
                    json.dumps(response_json, ensure_ascii=False),
                    1 if response.approved else 0,
                    resolved_at,
                    response.confirmation_id,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM a2ui_records WHERE confirmation_id = ?",
                (response.confirmation_id,),
            ).fetchone()
        return self._row_to_a2ui(row) if row else None

    def list_a2ui(self, conversation_id: str) -> list[A2UIRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM a2ui_records
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                """,
                (conversation_id,),
            ).fetchall()
        return [self._row_to_a2ui(r) for r in rows]

    def import_from_json(
        self,
        conversations: dict[str, Conversation],
        messages_dict: dict[str, list[ConversationMessage]],
    ) -> int:
        """一次性从 dev_store.json 导入；返回导入消息条数。"""
        imported = 0
        for conv in list(conversations.values()):
            self.upsert_conversation(conv)
        for msgs in list(messages_dict.values()):
            for msg in list(msgs):
                self.append_message(msg)
                imported += 1
        return imported

    def import_messages_dict(self, raw: dict[str, list[dict]]) -> int:
        imported = 0
        for items in list(raw.values()):
            for item in list(items):
                msgs = load_conversation_messages([item])
                for msg in msgs:
                    self.append_message(msg)
                    imported += 1
        return imported

    def delete_by_script_id(self, project_id: str, script_id: str) -> None:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM conversations WHERE project_id = ? AND script_id = ?",
                (project_id, script_id),
            ).fetchall()
            conv_ids = [row["id"] for row in rows]
            if conv_ids:
                placeholders = ",".join("?" * len(conv_ids))
                conn.execute(
                    f"DELETE FROM a2ui_records WHERE conversation_id IN ({placeholders})",
                    conv_ids,
                )
                conn.execute(
                    f"DELETE FROM conversation_messages WHERE conversation_id IN ({placeholders})",
                    conv_ids,
                )
            conn.execute(
                "DELETE FROM conversation_messages WHERE project_id = ? AND script_id = ?",
                (project_id, script_id),
            )
            conn.execute(
                "DELETE FROM conversations WHERE project_id = ? AND script_id = ?",
                (project_id, script_id),
            )
            conn.commit()

    def delete_by_project_id(self, project_id: str) -> None:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM conversations WHERE project_id = ?",
                (project_id,),
            ).fetchall()
            conv_ids = [row["id"] for row in rows]
            if conv_ids:
                placeholders = ",".join("?" * len(conv_ids))
                conn.execute(
                    f"DELETE FROM a2ui_records WHERE conversation_id IN ({placeholders})",
                    conv_ids,
                )
                conn.execute(
                    f"DELETE FROM conversation_messages WHERE conversation_id IN ({placeholders})",
                    conv_ids,
                )
            conn.execute(
                "DELETE FROM conversation_messages WHERE project_id = ?",
                (project_id,),
            )
            conn.execute("DELETE FROM conversations WHERE project_id = ?", (project_id,))
            conn.commit()

    def clear_all(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM a2ui_records")
            conn.execute("DELETE FROM conversation_messages")
            conn.execute("DELETE FROM conversations")
            conn.commit()

    @staticmethod
    def _parse_json(val: str | None) -> Any:
        if not val:
            return None
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return val

    def _row_to_conversation(self, row: sqlite3.Row) -> Conversation:
        status_raw = row["status"] or ConversationStatus.ACTIVE.value
        try:
            status = ConversationStatus(status_raw)
        except ValueError:
            status = ConversationStatus.ACTIVE
        return Conversation(
            id=row["id"],
            project_id=row["project_id"],
            script_id=row["script_id"],
            title=row["title"] or "",
            last_summary=row["last_summary"] or "",
            status=status,
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            last_round_token_usage=self._parse_json(row["last_round_token_usage"]) or {},
            total_token_usage=self._parse_json(row["total_token_usage"]) or {},
        )

    def _row_to_message(self, row: sqlite3.Row) -> ConversationMessage:
        content = self._parse_json(row["content"])
        if content is None:
            content = ""
        role_raw = row["role"] or MessageRole.USER.value
        try:
            role = MessageRole(role_raw)
        except ValueError:
            role = MessageRole.USER
        kind_raw = row["message_kind"] or MessageKind.DEFAULT.value
        try:
            kind = MessageKind(kind_raw)
        except ValueError:
            kind = MessageKind.DEFAULT
        return ConversationMessage(
            id=row["id"],
            conversation_id=row["conversation_id"],
            project_id=row["project_id"] or "",
            script_id=row["script_id"] or "",
            channel=row["channel"] or "master",
            agent_name=row["agent_name"] or "",
            step_id=row["step_id"] or "",
            role=role,
            content=content,
            tool_call_id=row["tool_call_id"] or "",
            message_kind=kind,
            created_at=row["created_at"] or "",
        )

    def _row_to_a2ui(self, row: sqlite3.Row) -> A2UIRecord:
        approved = row["approved"]
        return A2UIRecord(
            id=row["id"],
            conversation_id=row["conversation_id"],
            confirmation_id=row["confirmation_id"],
            kind=row["kind"] or "",
            title=row["title"] or "",
            request_json=self._parse_json(row["request_json"]) or {},
            response_json=self._parse_json(row["response_json"]),
            approved=bool(approved) if approved is not None else None,
            created_at=row["created_at"] or "",
            resolved_at=row["resolved_at"],
        )
