"""项目/剧本目录布局：data/projects/{project_id}/scripts/{script_id}/。"""

from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path
from typing import Any

from core.models.entities import Project, Script
from core.store.memory import MemoryStore


def resolve_data_root() -> Path:
    """解析 data 根目录（仓库根/data 或 SVG_DATA_ROOT）。"""
    override = os.getenv("SVG_DATA_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return (parent / "data").resolve()
    return (Path.cwd() / "data").resolve()


DATA_ROOT = resolve_data_root()
PROJECTS_ROOT = DATA_ROOT / "projects"


def project_dir(project_id: str) -> Path:
    return PROJECTS_ROOT / project_id


def script_dir(project_id: str, script_id: str) -> Path:
    return project_dir(project_id) / "scripts" / script_id


def script_media_dir(project_id: str, script_id: str) -> Path:
    return script_dir(project_id, script_id) / "assets" / "media"


def script_exports_dir(project_id: str, script_id: str) -> Path:
    return script_dir(project_id, script_id) / "assets" / "exports"


def rag_db_path(project_id: str) -> Path:
    """项目 RAG 向量索引 SQLite 路径。"""
    return project_dir(project_id) / "rag" / "embeddings.sqlite"


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_project_layout(project: Project) -> Path:
    """创建项目目录并写入 project.json 快照。"""
    root = project_dir(project.id)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    _write_json(root / "project.json", project.model_dump())
    return root


def ensure_script_layout(script: Script) -> Path:
    """创建剧本目录、assets 子目录并写入 script.json 快照。"""
    root = script_dir(script.project_id, script.id)
    script_media_dir(script.project_id, script.id).mkdir(parents=True, exist_ok=True)
    script_exports_dir(script.project_id, script.id).mkdir(parents=True, exist_ok=True)
    _write_json(root / "script.json", script.model_dump())
    return root


def sync_project_meta(store: MemoryStore, project_id: str) -> None:
    project = store.get_project(project_id)
    if project is None:
        return
    ensure_project_layout(project)


def sync_script_meta(store: MemoryStore, project_id: str, script_id: str) -> None:
    script = store.get_script(script_id)
    if script is None or script.project_id != project_id:
        return
    project = store.get_project(project_id)
    if project is not None:
        ensure_project_layout(project)
    ensure_script_layout(script)


def sync_all_meta(store: MemoryStore) -> None:
    """将 MemoryStore 中全部项目/剧本 meta 双写到目录。"""
    for project in list(store.projects.values()):
        ensure_project_layout(project)
    for script in list(store.scripts.values()):
        ensure_script_layout(script)


def relative_media_path(project_id: str, script_id: str, filename: str) -> str:
    """返回相对 data/ 的路径，便于存入 MediaAsset.url。"""
    rel = Path("projects") / project_id / "scripts" / script_id / "assets" / "media" / filename
    return rel.as_posix()


def parse_relative_media_path(relative: str) -> tuple[str, str, str] | None:
    """解析 projects/{pid}/scripts/{sid}/assets/media/{filename}。"""
    normalized = relative.replace("\\", "/").strip("/")
    parts = Path(normalized).parts
    if (
        len(parts) >= 6
        and parts[0] == "projects"
        and parts[2] == "scripts"
        and parts[4] == "assets"
        and parts[5] == "media"
    ):
        return parts[1], parts[3], parts[-1]
    return None


def media_api_path(project_id: str, script_id: str, filename: str) -> str:
    """前端/API 可访问的媒体文件 URL。"""
    from urllib.parse import quote

    safe_name = quote(filename, safe=".")
    return f"/api/projects/{project_id}/scripts/{script_id}/assets/media/{safe_name}"


def relative_export_path(project_id: str, script_id: str, filename: str) -> str:
    """返回相对 data/ 的成片路径。"""
    rel = Path("projects") / project_id / "scripts" / script_id / "assets" / "exports" / filename
    return rel.as_posix()


def parse_relative_export_path(relative: str) -> tuple[str, str, str] | None:
    """解析 projects/{pid}/scripts/{sid}/assets/exports/{filename}。"""
    normalized = relative.replace("\\", "/").strip("/")
    parts = Path(normalized).parts
    if (
        len(parts) >= 6
        and parts[0] == "projects"
        and parts[2] == "scripts"
        and parts[4] == "assets"
        and parts[5] == "exports"
    ):
        return parts[1], parts[3], parts[-1]
    return None


def export_api_path(project_id: str, script_id: str, filename: str) -> str:
    """前端/API 可访问的成片 URL。"""
    from urllib.parse import quote

    safe_name = quote(filename, safe=".")
    return f"/api/projects/{project_id}/scripts/{script_id}/assets/exports/{safe_name}"


def absolute_export_path(relative_url: str) -> Path | None:
    """将 projects/.../assets/exports/... 转为本地绝对路径。"""
    parsed = parse_relative_export_path(relative_url)
    if not parsed:
        return None
    project_id, script_id, filename = parsed
    path = script_exports_dir(project_id, script_id) / filename
    return path if path.is_file() else None


def _remove_tree(path: Path) -> None:
    """递归删除目录（Windows 只读文件兼容）。"""
    if not path.exists():
        return

    def _onerror(func, p, _exc_info) -> None:
        if not os.access(p, os.W_OK):
            os.chmod(p, stat.S_IWUSR)
            func(p)
        else:
            raise

    shutil.rmtree(path, onerror=_onerror)


def remove_script_dir(project_id: str, script_id: str) -> bool:
    """删除剧本目录树（含 assets/media）；成功或本就不存在返回 True。"""
    path = script_dir(project_id, script_id)
    if path.exists():
        _remove_tree(path)
    return not path.exists()


def remove_project_dir(project_id: str) -> bool:
    """删除 data/projects/{project_id}/ 整棵目录树；成功或本就不存在返回 True。"""
    path = project_dir(project_id)
    if path.exists():
        _remove_tree(path)
    return not path.exists()


def discover_projects_from_disk(store: MemoryStore) -> bool:
    """
    从 data/projects/ 导入 MemoryStore 中缺失的项目/剧本 meta（project.json、script.json）。
    用于 dev_store.json 与目录双写不同步时恢复项目列表；完整资产仍以 dev_store 为准。
    """
    if not PROJECTS_ROOT.is_dir():
        return False
    changed = False
    for proj_dir in PROJECTS_ROOT.iterdir():
        if not proj_dir.is_dir():
            continue
        meta_path = proj_dir / "project.json"
        if not meta_path.is_file():
            continue
        try:
            raw = json.loads(meta_path.read_text(encoding="utf-8"))
            project = Project.model_validate(raw)
        except (json.JSONDecodeError, OSError, ValueError):
            continue
        if project.id != proj_dir.name:
            project = project.model_copy(update={"id": proj_dir.name})
        if store.get_project(project.id) is None:
            store.add_project(project)
            changed = True
        scripts_root = proj_dir / "scripts"
        if not scripts_root.is_dir():
            continue
        for script_path_dir in scripts_root.iterdir():
            if not script_path_dir.is_dir():
                continue
            script_meta = script_path_dir / "script.json"
            if not script_meta.is_file():
                continue
            try:
                script_raw = json.loads(script_meta.read_text(encoding="utf-8"))
                script = Script.model_validate(script_raw)
            except (json.JSONDecodeError, OSError, ValueError):
                continue
            if script.id != script_path_dir.name:
                script = script.model_copy(update={"id": script_path_dir.name})
            if script.project_id != project.id:
                script = script.model_copy(update={"project_id": project.id})
            if not (script.created_at or "").strip():
                try:
                    from datetime import datetime, timezone

                    mtime = script_meta.stat().st_mtime
                    script = script.model_copy(
                        update={
                            "created_at": datetime.fromtimestamp(
                                mtime, tz=timezone.utc
                            ).isoformat()
                        }
                    )
                except OSError:
                    pass
            if store.get_script(script.id) is None:
                store.add_script(script)
                changed = True
    return changed


def sync_scripts_from_disk(store: MemoryStore) -> bool:
    """
    将 data/projects/*/scripts/*/script.json 中较新的字段合并进 MemoryStore。
    解决 dev_store.json 与磁盘 meta 不同步导致剧本正文/状态缺失。
    """
    if not PROJECTS_ROOT.is_dir():
        return False
    changed = False
    for proj_dir in PROJECTS_ROOT.iterdir():
        if not proj_dir.is_dir():
            continue
        scripts_root = proj_dir / "scripts"
        if not scripts_root.is_dir():
            continue
        for script_path_dir in scripts_root.iterdir():
            if not script_path_dir.is_dir():
                continue
            script_meta = script_path_dir / "script.json"
            if not script_meta.is_file():
                continue
            try:
                script_raw = json.loads(script_meta.read_text(encoding="utf-8"))
                disk_script = Script.model_validate(script_raw)
            except (json.JSONDecodeError, OSError, ValueError):
                continue
            if disk_script.id != script_path_dir.name:
                disk_script = disk_script.model_copy(update={"id": script_path_dir.name})
            if disk_script.project_id != proj_dir.name:
                disk_script = disk_script.model_copy(update={"project_id": proj_dir.name})

            existing = store.get_script(disk_script.id)
            if existing is None:
                if store.get_project(disk_script.project_id) is not None:
                    store.add_script(disk_script)
                    changed = True
                continue

            updates: dict[str, Any] = {}
            disk_md = (disk_script.content_md or "").strip()
            existing_md = (existing.content_md or "").strip()
            if disk_md and len(disk_md) > len(existing_md):
                updates["content_md"] = disk_script.content_md
            for field in (
                "title",
                "status",
                "duration_sec",
                "style_mode",
                "style_locked",
                "plan_version",
                "created_at",
            ):
                disk_val = getattr(disk_script, field, None)
                existing_val = getattr(existing, field, None)
                if disk_val is not None and disk_val != existing_val:
                    if field == "content_md":
                        continue
                    # 已有 created_at 时不覆盖为空
                    if field == "created_at" and (not disk_val) and existing_val:
                        continue
                    updates[field] = disk_val
            if not (existing.created_at or "").strip() and not updates.get("created_at"):
                # 历史剧本无创建时间时，用 script.json mtime 回填，保证整体看板排序稳定
                try:
                    mtime = script_meta.stat().st_mtime
                    from datetime import datetime, timezone

                    updates["created_at"] = datetime.fromtimestamp(
                        mtime, tz=timezone.utc
                    ).isoformat()
                except OSError:
                    pass
            if updates:
                store.scripts[disk_script.id] = existing.model_copy(update=updates)
                changed = True
    return changed
