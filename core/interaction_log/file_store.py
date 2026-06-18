"""交互记录 JSONL 文件落盘：按日期写入 data/logs/interactions/。"""

import json
from datetime import datetime, timezone
from pathlib import Path

from core.interaction_log.models import InteractionRecord

DEFAULT_LOG_DIR = Path("data/logs/interactions")


class InteractionFileStore:
    """将 InteractionRecord 追加到按日分片的 JSONL 文件。"""

    def __init__(self, log_dir: Path | str = DEFAULT_LOG_DIR) -> None:
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def log_dir(self) -> Path:
        return self._dir

    def _path_for_date(self, date_str: str) -> Path:
        return self._dir / f"{date_str}.jsonl"

    def _date_from_record(self, record: InteractionRecord) -> str:
        if record.created_at:
            return record.created_at[:10]
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def append(self, record: InteractionRecord) -> None:
        date_str = self._date_from_record(record)
        path = self._path_for_date(date_str)
        line = json.dumps(record.model_dump(), ensure_ascii=False)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def list_log_files(self) -> list[dict[str, str | int]]:
        """列出可用 JSONL 文件及大小（字节）。"""
        files: list[dict[str, str | int]] = []
        for path in sorted(self._dir.glob("*.jsonl"), reverse=True):
            stat = path.stat()
            files.append(
                {
                    "date": path.stem,
                    "path": str(path),
                    "size_bytes": stat.st_size,
                }
            )
        return files

    def read_tail(self, date: str | None = None, limit: int = 100) -> list[InteractionRecord]:
        """读取指定日期（默认今天）JSONL 文件末尾若干条。"""
        date_str = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self._path_for_date(date_str)
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
