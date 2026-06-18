"""开发态 MemoryStore JSON 持久化（避免 uvicorn reload 丢失会话）。"""

import json
import os
import threading
from pathlib import Path

from core.models.entities import (
    AssetReference,
    PlanDocument,
    Project,
    Script,
    TextAsset,
    VideoPlan,
)
from core.store.memory import MemoryStore

DEFAULT_PATH = Path("data/dev_store.json")
_ENV_FLAG = os.getenv("SVG_PERSIST_STORE", "1").strip().lower()
_ENABLED = _ENV_FLAG not in ("0", "false", "no", "off")

_lock = threading.Lock()
_pending = False


def is_enabled() -> bool:
    return _ENABLED


def load_store(store: MemoryStore, path: Path | None = None) -> bool:
    """从 JSON 恢复 MemoryStore；文件不存在则跳过。"""
    if not _ENABLED:
        return False
    file_path = path or DEFAULT_PATH
    if not file_path.exists():
        return False
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False

    store.projects = {
        k: Project.model_validate(v) for k, v in raw.get("projects", {}).items()
    }
    store.scripts = {
        k: Script.model_validate(v) for k, v in raw.get("scripts", {}).items()
    }
    store.text_assets = {
        k: TextAsset.model_validate(v) for k, v in raw.get("text_assets", {}).items()
    }
    store.references = {
        k: AssetReference.model_validate(v) for k, v in raw.get("references", {}).items()
    }
    store.plans = {
        k: PlanDocument.model_validate(v) for k, v in raw.get("plans", {}).items()
    }
    store.video_plans = {
        k: VideoPlan.model_validate(v) for k, v in raw.get("video_plans", {}).items()
    }
    store._script_plans = dict(raw.get("script_plans", {}))
    return True


def save_store(store: MemoryStore, path: Path | None = None) -> None:
    """立即写入 JSON。"""
    if not _ENABLED:
        return
    file_path = path or DEFAULT_PATH
    file_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "projects": {k: v.model_dump() for k, v in store.projects.items()},
        "scripts": {k: v.model_dump() for k, v in store.scripts.items()},
        "text_assets": {k: v.model_dump() for k, v in store.text_assets.items()},
        "references": {k: v.model_dump() for k, v in store.references.items()},
        "plans": {k: v.model_dump() for k, v in store.plans.items()},
        "video_plans": {k: v.model_dump() for k, v in store.video_plans.items()},
        "script_plans": dict(store._script_plans),
    }
    with _lock:
        file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def schedule_save(store: MemoryStore, path: Path | None = None, delay_sec: float = 0.5) -> None:
    """防抖写入（reload 频繁时减少 IO）。"""
    global _pending
    if not _ENABLED:
        return
    if _pending:
        return
    _pending = True

    def _run() -> None:
        global _pending
        import time

        time.sleep(delay_sec)
        save_store(store, path)
        _pending = False

    threading.Thread(target=_run, daemon=True).start()
