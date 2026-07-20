"""pytest 会话级 data/ 隔离与测试项目泄漏清理。"""

from __future__ import annotations

import json
from pathlib import Path

from core.store import persist, project_paths


def cancel_pending_persist() -> None:
    """取消尚未执行的防抖落盘，避免 rebind 后写入错误路径。"""
    with persist._lock:
        timer = persist._save_timer
        if timer is not None:
            timer.cancel()
            persist._save_timer = None


def resolve_real_data_root() -> Path:
    """返回仓库真实 data/ 根目录（不受会话 rebind 影响）。"""
    return project_paths.resolve_data_root().resolve()


def snapshot_project_ids(data_root: Path) -> set[str]:
    """从 dev_store.json 与 projects/*/project.json 收集项目 ID 快照。"""
    ids: set[str] = set()

    store_path = data_root / "dev_store.json"
    if store_path.is_file():
        try:
            raw = json.loads(store_path.read_text(encoding="utf-8"))
            projects = raw.get("projects")
            if isinstance(projects, dict):
                ids.update(str(pid) for pid in projects.keys())
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    projects_root = data_root / "projects"
    if projects_root.is_dir():
        for proj_dir in projects_root.iterdir():
            if not proj_dir.is_dir():
                continue
            meta_path = proj_dir / "project.json"
            if meta_path.is_file():
                ids.add(proj_dir.name)
            elif proj_dir.name.startswith("proj_"):
                ids.add(proj_dir.name)

    return ids


def rebind_conversation_storage() -> None:
    """将 AppState 对话 SQLite 绑定到当前 DATA_ROOT，避免测试清空真实 conversations.db。"""
    from apps.api.state import state
    from core.conversation import ConversationStore
    from core.conversation.sqlite_store import ConversationSqliteStore

    db_path = project_paths.DATA_ROOT / "conversations.db"
    state.conversation_sqlite = ConversationSqliteStore(db_path=db_path)
    state.conversations = ConversationStore(sqlite_store=state.conversation_sqlite)
    state.confirmation_manager.set_sqlite_store(state.conversation_sqlite)
    state.super_video_master.rebind_conversation_stores(
        state.conversations,
        state.conversation_index,
    )


def rebind_data_root(session_root: Path) -> None:
    """将会话内持久化路径绑定到临时 data 根目录。"""
    cancel_pending_persist()
    session_root.mkdir(parents=True, exist_ok=True)
    projects_root = session_root / "projects"
    projects_root.mkdir(parents=True, exist_ok=True)
    import os

    os.environ["SVG_DATA_ROOT"] = str(session_root.resolve())
    project_paths.DATA_ROOT = session_root
    project_paths.PROJECTS_ROOT = projects_root
    persist.DEFAULT_PATH = session_root / "dev_store.json"
    rebind_conversation_storage()


def reset_app_state_for_tests() -> None:
    """清空全局 AppState，避免从真实 dev_store 继续读写。"""
    from apps.api.state import state
    from core.llm.agent.config_manager import set_agent_config_manager

    rebind_conversation_storage()
    set_agent_config_manager(None)
    state.store.clear()
    state.conversation_index.clear()
    state.conversations.clear()
    state.conversation_sqlite.clear_all()
    state.persist_store(immediate=True)


def cleanup_projects_by_ids(project_ids: set[str], data_root: Path) -> None:
    """在指定 data 根目录下删除泄漏的测试项目（仅 tests/ 调用）。"""
    if not project_ids:
        return

    from apps.api.state import delete_project, state
    from core.store.persist import load_store

    cancel_pending_persist()
    rebind_data_root(data_root)
    state.store.clear()
    load_store(
        state.store,
        conversation_index=state.conversation_index,
        conversation_store=state.conversations,
    )

    for project_id in sorted(project_ids):
        try:
            delete_project(project_id)
        except ValueError:
            continue


def session_should_skip_isolation(session) -> bool:
    """当本次会话仅包含 live/integration 用例时跳过 data 隔离。"""
    non_isolated = [
        item
        for item in session.items
        if item.get_closest_marker("live") is None
        and item.get_closest_marker("integration") is None
    ]
    return not non_isolated
