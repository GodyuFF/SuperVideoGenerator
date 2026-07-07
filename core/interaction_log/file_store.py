"""交互记录 JSONL 文件落盘：按项目 + 日期写入 data/logs/interactions/{project_id}/。"""

import json
from datetime import datetime, timezone
from pathlib import Path

from core.interaction_log.models import InteractionRecord

DEFAULT_LOG_DIR = Path("data/logs/interactions")
UNKNOWN_PROJECT = "_unknown"


class InteractionFileStore:
    """将 InteractionRecord 追加到按项目、日期分片的 JSONL 文件。"""

    def __init__(self, log_dir: Path | str = DEFAULT_LOG_DIR) -> None:
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def log_dir(self) -> Path:
        return self._dir

    def _project_key(self, project_id: str) -> str:
        pid = (project_id or "").strip()
        return pid or UNKNOWN_PROJECT

    def _project_dir(self, project_id: str) -> Path:
        path = self._dir / self._project_key(project_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _path_for(self, project_id: str, date_str: str) -> Path:
        return self._project_dir(project_id) / f"{date_str}.jsonl"

    def _date_from_record(self, record: InteractionRecord) -> str:
        if record.created_at:
            return record.created_at[:10]
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def append(self, record: InteractionRecord) -> None:
        date_str = self._date_from_record(record)
        path = self._path_for(record.project_id, date_str)
        line = json.dumps(record.model_dump(), ensure_ascii=False)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def list_log_files(
        self, project_id: str | None = None
    ) -> list[dict[str, str | int]]:
        """列出 JSONL 文件；可按 project_id 过滤。"""
        files: list[dict[str, str | int]] = []

        def add_file(path: Path, pid: str) -> None:
            stat = path.stat()
            files.append(
                {
                    "project_id": pid,
                    "date": path.stem,
                    "path": str(path),
                    "size_bytes": stat.st_size,
                }
            )

        if project_id:
            proj_dir = self._dir / self._project_key(project_id)
            if proj_dir.is_dir():
                for path in sorted(proj_dir.glob("*.jsonl"), reverse=True):
                    add_file(path, self._project_key(project_id))
        else:
            for proj_path in sorted(self._dir.iterdir()):
                if not proj_path.is_dir():
                    continue
                pid = proj_path.name
                for path in sorted(proj_path.glob("*.jsonl"), reverse=True):
                    add_file(path, pid)
            for path in sorted(self._dir.glob("*.jsonl"), reverse=True):
                add_file(path, "")

        files.sort(key=lambda f: (str(f.get("project_id", "")), str(f["date"])), reverse=True)
        return files

    def delete_log_file(self, project_id: str, date: str) -> bool:
        """删除指定项目、日期的 JSONL 文件；不存在视为成功。"""
        day = date.strip()
        if not day:
            return False
        pid = self._project_key(project_id)
        path = self._dir / pid / f"{day}.jsonl"
        if path.is_file():
            path.unlink()
        proj_dir = self._dir / pid
        if proj_dir.is_dir() and not any(proj_dir.iterdir()):
            proj_dir.rmdir()
        return not path.exists()

    def read_tail(
        self,
        date: str | None = None,
        limit: int = 100,
        *,
        project_id: str | None = None,
    ) -> list[InteractionRecord]:
        """读取指定项目、日期 JSONL 文件末尾若干条。"""
        date_str = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        pid = self._project_key(project_id or "")
        path = self._path_for(pid if project_id else "", date_str)
        if not path.exists() and project_id:
            legacy = self._dir / f"{date_str}.jsonl"
            path = legacy if legacy.exists() else path
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        tail = lines[-limit:] if limit else lines
        result: list[InteractionRecord] = []
        for line in tail:
            if not line.strip():
                continue
            data = json.loads(line)
            result.append(InteractionRecord(**data))
        return result
