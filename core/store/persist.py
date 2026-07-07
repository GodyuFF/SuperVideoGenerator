"""开发态 MemoryStore JSON 持久化（避免 uvicorn reload 丢失会话）。"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from core.models.entities import (
    AssetReference,
    Conversation,
    EditTimeline,
    MediaAsset,
    PlanDocument,
    Project,
    Script,
    TextAsset,
    VideoPlan,
)
from core.store.memory import MemoryStore
from core.store.project_paths import DATA_ROOT

_CONV_MESSAGES_KEY = "conversation_messages"

DEFAULT_PATH = DATA_ROOT / "dev_store.json"
_ENV_FLAG = os.getenv("SVG_PERSIST_STORE", "1").strip().lower()
_ENABLED = _ENV_FLAG not in ("0", "false", "no", "off")

_lock = threading.Lock()
_save_timer: threading.Timer | None = None
_persist_hooks: dict[str, Any] = {}


def is_enabled() -> bool:
    return _ENABLED


def configure_persist_hooks(
    *,
    conversation_index: Any | None = None,
    conversation_store: Any | None = None,
    path: Path | None = None,
) -> None:
    """由 AppState 注册，使 schedule_save(store) 也能带上对话 index。"""
    global _persist_hooks
    _persist_hooks = {
        "conversation_index": conversation_index,
        "conversation_store": conversation_store,
        "path": path,
    }


def _resolve_persist_kwargs(
    path: Path | None,
    conversation_index: Any | None,
    conversation_store: Any | None,
) -> tuple[Path | None, Any | None, Any | None]:
    hook_path = _persist_hooks.get("path")
    hook_index = _persist_hooks.get("conversation_index")
    hook_store = _persist_hooks.get("conversation_store")
    return (
        path if path is not None else hook_path,
        conversation_index if conversation_index is not None else hook_index,
        conversation_store if conversation_store is not None else hook_store,
    )


def _merge_preserve_keys(data: dict[str, Any], file_path: Path) -> None:
    """schedule_save 未传 conversations 时保留文件中已有字段，避免误删。"""
    if not file_path.is_file():
        return
    try:
        existing = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if "conversations" not in data and isinstance(existing.get("conversations"), dict):
        data["conversations"] = existing["conversations"]
    if _CONV_MESSAGES_KEY not in data and isinstance(existing.get(_CONV_MESSAGES_KEY), dict):
        data[_CONV_MESSAGES_KEY] = existing[_CONV_MESSAGES_KEY]


def load_store(
    store: MemoryStore,
    path: Path | None = None,
    *,
    conversation_index: Any | None = None,
    conversation_store: Any | None = None,
) -> bool:
    """从 JSON 恢复 MemoryStore；并扫描 data/projects/ 补齐缺失的项目 meta。"""
    if not _ENABLED:
        return False
    file_path = path or DEFAULT_PATH
    loaded_json = False
    if file_path.exists():
        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            raw = None
        if raw is not None:
            store.projects = {
                k: Project.model_validate(v) for k, v in raw.get("projects", {}).items()
            }
            store.scripts = {
                k: Script.model_validate(v) for k, v in raw.get("scripts", {}).items()
            }
            store.text_assets = {}
            from core.models.image_text_asset import upgrade_text_asset_content

            for k, v in raw.get("text_assets", {}).items():
                try:
                    asset = TextAsset.model_validate(v)
                    store.text_assets[k] = upgrade_text_asset_content(asset)
                except Exception:
                    from core.llm.agent.asset_content import normalize_asset_content

                    if isinstance(v, dict) and "content" in v and not isinstance(
                        v["content"], dict
                    ):
                        v = dict(v)
                        v["content"] = normalize_asset_content(
                            v["content"], asset_type=v.get("type")
                        )
                    asset = TextAsset.model_validate(v)
                    store.text_assets[k] = upgrade_text_asset_content(asset)
            store.references = {
                k: AssetReference.model_validate(v)
                for k, v in raw.get("references", {}).items()
            }
            store.plans = {
                k: PlanDocument.model_validate(v) for k, v in raw.get("plans", {}).items()
            }
            store.video_plans = {
                k: VideoPlan.model_validate(v) for k, v in raw.get("video_plans", {}).items()
            }
            store.edit_timelines = {
                k: EditTimeline.model_validate(v)
                for k, v in raw.get("edit_timelines", {}).items()
            }
            store.media_assets = {
                k: MediaAsset.model_validate(v) for k, v in raw.get("media_assets", {}).items()
            }
            store._script_plans = dict(raw.get("script_plans", {}))

            if conversation_index is not None and conversation_store is not None:
                convs = {
                    k: Conversation.model_validate(v)
                    for k, v in raw.get("conversations", {}).items()
                }
                conversation_index.load_dict(convs)
                from core.conversation.store import (
                    ConversationMessage,
                    load_conversation_messages,
                )

                msg_data: dict[str, list[ConversationMessage]] = {}
                for k, items in raw.get(_CONV_MESSAGES_KEY, {}).items():
                    msg_data[k] = load_conversation_messages(items)
                conversation_store.load_dict(msg_data)
            loaded_json = True

    from core.store.asset_disk_sync import merge_script_bundles_from_disk
    from core.store.project_paths import discover_projects_from_disk, sync_scripts_from_disk

    bundles_merged = merge_script_bundles_from_disk(store)
    discovered = discover_projects_from_disk(store)
    scripts_synced = sync_scripts_from_disk(store)
    if discovered or scripts_synced or bundles_merged:
        save_store(
            store,
            file_path,
            conversation_index=conversation_index,
            conversation_store=conversation_store,
        )

    return loaded_json or discovered or scripts_synced or bundles_merged or bool(store.projects)


def save_store(
    store: MemoryStore,
    path: Path | None = None,
    *,
    conversation_index: Any | None = None,
    conversation_store: Any | None = None,
) -> None:
    """立即写入 JSON。"""
    if not _ENABLED:
        return
    file_path, conv_index, conv_store = _resolve_persist_kwargs(
        path, conversation_index, conversation_store
    )
    file_path = file_path or DEFAULT_PATH
    file_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "projects": {k: v.model_dump() for k, v in store.projects.items()},
        "scripts": {k: v.model_dump() for k, v in store.scripts.items()},
        "text_assets": {k: v.model_dump() for k, v in store.text_assets.items()},
        "references": {k: v.model_dump() for k, v in store.references.items()},
        "plans": {k: v.model_dump() for k, v in store.plans.items()},
        "video_plans": {k: v.model_dump() for k, v in store.video_plans.items()},
        "edit_timelines": {k: v.model_dump() for k, v in store.edit_timelines.items()},
        "media_assets": {k: v.model_dump() for k, v in store.media_assets.items()},
        "script_plans": dict(store._script_plans),
    }
    if conv_index is not None:
        data["conversations"] = {
            k: v.model_dump() for k, v in conv_index.conversations.items()
        }

    if conv_store is not None:
        data[_CONV_MESSAGES_KEY] = {
            k: [m.model_dump() for m in msgs]
            for k, msgs in conv_store.messages.items()
        }

    _merge_preserve_keys(data, file_path)

    with _lock:
        file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    try:
        from core.store.asset_disk_sync import write_script_bundles
        from core.store.project_paths import sync_all_meta

        sync_all_meta(store)
        write_script_bundles(store)
    except OSError:
        pass


def schedule_save(
    store: MemoryStore,
    path: Path | None = None,
    delay_sec: float = 0.5,
    *,
    conversation_index: Any | None = None,
    conversation_store: Any | None = None,
    immediate: bool = False,
) -> None:
    """防抖写入；重复调用会推迟计时而非丢弃。"""
    global _save_timer
    if not _ENABLED:
        return
    if immediate:
        with _lock:
            if _save_timer is not None:
                _save_timer.cancel()
                _save_timer = None
        save_store(
            store,
            path,
            conversation_index=conversation_index,
            conversation_store=conversation_store,
        )
        return

    def _run() -> None:
        global _save_timer
        save_store(
            store,
            path,
            conversation_index=conversation_index,
            conversation_store=conversation_store,
        )
        with _lock:
            _save_timer = None

    with _lock:
        if _save_timer is not None:
            _save_timer.cancel()
        _save_timer = threading.Timer(delay_sec, _run)
        _save_timer.daemon = True
        _save_timer.start()
