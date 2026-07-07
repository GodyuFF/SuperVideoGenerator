"""资产 bundle 双写与 schedule_save 防抖测试。"""

import json
import time
from pathlib import Path

import pytest

from core.models.entities import AssetScope, Project, Script, TextAsset, TextAssetType
from core.store.asset_disk_sync import (
    BUNDLE_FILENAME,
    merge_script_bundles_from_disk,
    write_script_bundles,
)
from core.store.memory import MemoryStore
from core.store.persist import load_store, save_store, schedule_save


def test_schedule_save_reschedules_not_drops(tmp_path, monkeypatch):
    store_path = tmp_path / "dev_store.json"
    monkeypatch.setattr("core.store.persist.DEFAULT_PATH", store_path)
    monkeypatch.setattr("core.store.persist._ENABLED", True)

    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    schedule_save(store, delay_sec=0.3)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    schedule_save(store, delay_sec=0.3)
    time.sleep(0.6)

    loaded = json.loads(store_path.read_text(encoding="utf-8"))
    assert project.id in loaded["projects"]
    assert script.id in loaded["scripts"]


def test_script_bundle_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("core.store.project_paths.DATA_ROOT", tmp_path)
    monkeypatch.setattr("core.store.project_paths.PROJECTS_ROOT", tmp_path / "projects")

    store = MemoryStore()
    project = Project(title="老猫项目")
    store.add_project(project)
    script = Script(project_id=project.id, title="老猫吃鱼")
    store.add_script(script)
    asset = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="阿福",
        content={"summary": "老猫", "description": "橘猫"},
    )
    store.add_text_asset(asset)

    write_script_bundles(store)
    bundle = tmp_path / "projects" / project.id / "scripts" / script.id / BUNDLE_FILENAME
    assert bundle.is_file()

    empty = MemoryStore()
    empty.add_project(project)
    empty.add_script(script)
    assert merge_script_bundles_from_disk(empty) is True
    assert asset.id in empty.text_assets
    assert empty.text_assets[asset.id].name == "阿福"


def test_load_store_merges_bundle_when_dev_store_sparse(tmp_path, monkeypatch):
    store_path = tmp_path / "dev_store.json"
    projects_root = tmp_path / "projects"
    monkeypatch.setattr("core.store.persist.DEFAULT_PATH", store_path)
    monkeypatch.setattr("core.store.project_paths.DATA_ROOT", tmp_path)
    monkeypatch.setattr("core.store.project_paths.PROJECTS_ROOT", projects_root)
    monkeypatch.setattr("core.store.persist._ENABLED", True)

    full = MemoryStore()
    project = Project(title="p")
    full.add_project(project)
    script = Script(project_id=project.id, title="s", content_md="# md")
    full.add_script(script)
    char = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="角色",
        content={"summary": "x"},
    )
    full.add_text_asset(char)
    write_script_bundles(full)

    sparse = {
        "projects": {project.id: project.model_dump()},
        "scripts": {script.id: script.model_dump()},
        "text_assets": {},
        "references": {},
        "plans": {},
        "video_plans": {},
        "edit_timelines": {},
        "media_assets": {},
        "script_plans": {},
    }
    store_path.write_text(json.dumps(sparse), encoding="utf-8")

    loaded = MemoryStore()
    assert load_store(loaded, store_path) is True
    assert char.id in loaded.text_assets
