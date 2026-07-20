"""SQLite 持久化：所有 LLM / HTTP / 规则回退交互记录。"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from core.interaction_log.models import InteractionRecord

DEFAULT_DB_PATH = Path("data/interaction_logs.db")

_INSERT_SQL = """
INSERT INTO interaction_logs (
    id, created_at, kind, source, project_id, script_id,
    agent_name, step_id, provider, model, method, url,
    status_code, duration_ms, summary, request_body,
    response_body, error, meta
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""


class InteractionLogStore:
    """交互日志 SQLite 仓储。"""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @property
    def db_path(self) -> Path:
        """数据库文件路径。"""
        return self._path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS interaction_logs (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    source TEXT,
                    project_id TEXT,
                    script_id TEXT,
                    agent_name TEXT,
                    step_id TEXT,
                    provider TEXT,
                    model TEXT,
                    method TEXT,
                    url TEXT,
                    status_code INTEGER,
                    duration_ms REAL,
                    summary TEXT,
                    request_body TEXT,
                    response_body TEXT,
                    error TEXT,
                    meta TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ilog_script ON interaction_logs(script_id, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ilog_project ON interaction_logs(project_id, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ilog_kind ON interaction_logs(kind, created_at)"
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.commit()

    @staticmethod
    def _row_values(record: InteractionRecord) -> tuple[Any, ...]:
        """将 InteractionRecord 转为 INSERT 参数元组。"""
        return (
            record.id,
            record.created_at,
            record.kind,
            record.source,
            record.project_id,
            record.script_id,
            record.agent_name,
            record.step_id,
            record.provider,
            record.model,
            record.method,
            record.url,
            record.status_code,
            record.duration_ms,
            record.summary,
            json.dumps(record.request_body, ensure_ascii=False)
            if record.request_body is not None
            else None,
            json.dumps(record.response_body, ensure_ascii=False)
            if isinstance(record.response_body, (dict, list))
            else record.response_body,
            record.error,
            json.dumps(record.meta, ensure_ascii=False) if record.meta else None,
        )

    def _ensure_created_at(self, record: InteractionRecord) -> InteractionRecord:
        """补全缺失的 created_at 字段。"""
        if not record.created_at:
            record.created_at = datetime.now(timezone.utc).isoformat()
        return record

    def append(self, record: InteractionRecord) -> InteractionRecord:
        self._ensure_created_at(record)
        with self._connect() as conn:
            conn.execute(_INSERT_SQL, self._row_values(record))
            conn.commit()
        return record

    def append_many(self, records: Sequence[InteractionRecord]) -> list[InteractionRecord]:
        """批量插入多条记录（单事务）。"""
        if not records:
            return []
        prepared = [self._ensure_created_at(r) for r in records]
        with self._connect() as conn:
            conn.executemany(_INSERT_SQL, [self._row_values(r) for r in prepared])
            conn.commit()
        return list(prepared)

    def list_records(
        self,
        script_id: str | None = None,
        project_id: str | None = None,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[InteractionRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if script_id:
            clauses.append("script_id = ?")
            params.append(script_id)
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        sql = f"SELECT * FROM interaction_logs {where} ORDER BY created_at DESC LIMIT ?"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_record(r) for r in rows]

    def count_llm_calls(
        self,
        script_id: str | None = None,
        project_id: str | None = None,
    ) -> int:
        clauses = ["kind = 'llm_response'"]
        params: list[Any] = []
        if script_id:
            clauses.append("script_id = ?")
            params.append(script_id)
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        where = "WHERE " + " AND ".join(clauses)
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS c FROM interaction_logs {where}", params
            ).fetchone()
        return int(row["c"]) if row else 0

    def delete_records(
        self,
        *,
        project_id: str,
        date: str,
        script_id: str | None = None,
    ) -> int:
        """删除指定项目、日期（created_at 前缀 YYYY-MM-DD）的 SQLite 记录。"""
        pid = project_id.strip()
        day = date.strip()
        if not pid or not day:
            return 0
        clauses = ["project_id = ?", "created_at LIKE ?"]
        params: list[Any] = [pid, f"{day}%"]
        if script_id:
            clauses.append("script_id = ?")
            params.append(script_id)
        where = "WHERE " + " AND ".join(clauses)
        with self._connect() as conn:
            cur = conn.execute(f"DELETE FROM interaction_logs {where}", params)
            conn.commit()
            return int(cur.rowcount or 0)

    def clear_all(self) -> None:
        """清空全部交互日志（不删除 db 文件，避免 Windows 文件锁）。"""
        with self._connect() as conn:
            conn.execute("DELETE FROM interaction_logs")
            conn.commit()

    def delete_older_than(
        self,
        days: int,
        *,
        kinds: Sequence[str] = ("api_request",),
    ) -> int:
        """删除 created_at 早于指定天数的指定 kind 记录。"""
        if days <= 0:
            return 0
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        kind_list = [k.strip() for k in kinds if k.strip()]
        if not kind_list:
            return 0
        placeholders = ",".join("?" for _ in kind_list)
        sql = (
            f"DELETE FROM interaction_logs WHERE created_at < ? AND kind IN ({placeholders})"
        )
        params: list[Any] = [cutoff, *kind_list]
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            conn.commit()
            return int(cur.rowcount or 0)

    def vacuum(self) -> None:
        """回收 SQLite 文件空间（维护脚本用）。"""
        with self._connect() as conn:
            conn.execute("VACUUM")

    @staticmethod
    def _parse_json(val: str | None) -> Any:
        if not val:
            return None
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return val

    def _row_to_record(self, row: sqlite3.Row) -> InteractionRecord:
        return InteractionRecord(
            id=row["id"],
            created_at=row["created_at"],
            kind=row["kind"],
            source=row["source"] or "",
            project_id=row["project_id"] or "",
            script_id=row["script_id"] or "",
            agent_name=row["agent_name"] or "",
            step_id=row["step_id"] or "",
            provider=row["provider"] or "",
            model=row["model"] or "",
            method=row["method"] or "",
            url=row["url"] or "",
            status_code=row["status_code"],
            duration_ms=row["duration_ms"],
            summary=row["summary"] or "",
            request_body=self._parse_json(row["request_body"]),
            response_body=self._parse_json(row["response_body"]),
            error=row["error"],
            meta=self._parse_json(row["meta"]) or {},
        )
