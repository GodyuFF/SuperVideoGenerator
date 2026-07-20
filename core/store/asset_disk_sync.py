"""剧本级资产 bundle 双写：重启后从 data/projects/.../store_bundle.json 恢复。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.models.entities import (
    AssetReference,
    EditTimeline,
    MediaAsset,
    PlanDocument,
    TextAsset,
    VideoPlan,
)
from core.store.memory import MemoryStore
from core.store.project_paths import script_dir

logger = logging.getLogger("core.store.asset_disk_sync")

BUNDLE_FILENAME = "store_bundle.json"


def bundle_path(project_id: str, script_id: str) -> Path:
    return script_dir(project_id, script_id) / BUNDLE_FILENAME


def _collect_script_bundle(store: MemoryStore, project_id: str, script_id: str) -> dict[str, Any]:
    text_ids: set[str] = set()
    for asset in store.list_assets_for_script(script_id):
        text_ids.add(asset.id)

    media_ids: set[str] = {
        m.id for m in store.list_media_for_script(script_id)
    }
    ref_ids: set[str] = set()
    for ref in store.references.values():
        if ref.script_id == script_id or ref.source_id in text_ids or ref.target_id in text_ids:
            ref_ids.add(ref.id)

    vp = store.get_video_plan_for_script(script_id)
    timeline = store.get_edit_timeline_for_script(script_id)
    plan = store.get_plan(script_id)

    return {
        "project_id": project_id,
        "script_id": script_id,
        "text_assets": {
            aid: store.text_assets[aid].model_dump()
            for aid in text_ids
            if aid in store.text_assets
        },
        "media_assets": {
            mid: store.media_assets[mid].model_dump()
            for mid in media_ids
            if mid in store.media_assets
        },
        "references": {
            rid: store.references[rid].model_dump()
            for rid in ref_ids
            if rid in store.references
        },
        "video_plans": {vp.id: vp.model_dump()} if vp else {},
        "edit_timelines": {timeline.id: timeline.model_dump()} if timeline else {},
        "plans": {f"{script_id}_v{plan.version}": plan.model_dump()} if plan else {},
        "script_plans": {script_id: store._script_plans.get(script_id)} if plan else {},
    }


def write_script_bundles(store: MemoryStore) -> None:
    """将各剧本资产快照写入磁盘。"""
    for script in store.scripts.values():
        path = bundle_path(script.project_id, script.id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = _collect_script_bundle(store, script.project_id, script.id)
            if not any(
                payload[k]
                for k in (
                    "text_assets",
                    "media_assets",
                    "video_plans",
                    "edit_timelines",
                )
            ):
                if path.is_file():
                    path.unlink(missing_ok=True)
                continue
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("写入 store_bundle 失败 script=%s: %s", script.id, exc)


def _merge_bundle_into_store(store: MemoryStore, raw: dict[str, Any]) -> bool:
    changed = False
    script_id = str(raw.get("script_id", ""))

    for aid, item in (raw.get("text_assets") or {}).items():
        if aid in store.text_assets:
            continue
        try:
            store.text_assets[aid] = TextAsset.model_validate(item)
            changed = True
        except (ValueError, TypeError):
            continue

    for mid, item in (raw.get("media_assets") or {}).items():
        if mid in store.media_assets:
            continue
        try:
            store.media_assets[mid] = MediaAsset.model_validate(item)
            changed = True
        except (ValueError, TypeError):
            continue

    for rid, item in (raw.get("references") or {}).items():
        if rid in store.references:
            continue
        try:
            store.references[rid] = AssetReference.model_validate(item)
            changed = True
        except (ValueError, TypeError):
            continue

    for pid, item in (raw.get("video_plans") or {}).items():
        if pid in store.video_plans:
            continue
        try:
            plan = VideoPlan.model_validate(item)
            store.video_plans[pid] = plan
            changed = True
        except (ValueError, TypeError):
            continue

    for tid, item in (raw.get("edit_timelines") or {}).items():
        if tid in store.edit_timelines:
            continue
        try:
            store.edit_timelines[tid] = EditTimeline.model_validate(item)
            changed = True
        except (ValueError, TypeError):
            continue

    for pk, item in (raw.get("plans") or {}).items():
        if pk in store.plans:
            continue
        try:
            store.plans[pk] = PlanDocument.model_validate(item)
            changed = True
        except (ValueError, TypeError):
            continue

    for sid, key in (raw.get("script_plans") or {}).items():
        if sid == script_id and key and not store._script_plans.get(sid):
            store._script_plans[sid] = key
            changed = True

    return changed


def merge_script_bundles_from_disk(store: MemoryStore) -> bool:
    """从各剧本 store_bundle.json 合并 dev_store 中缺失的资产。"""
    from core.store.project_paths import PROJECTS_ROOT

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
            bundle = script_path_dir / BUNDLE_FILENAME
            if not bundle.is_file():
                continue
            try:
                raw = json.loads(bundle.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, ValueError):
                continue
            if _merge_bundle_into_store(store, raw):
                changed = True
    return changed
