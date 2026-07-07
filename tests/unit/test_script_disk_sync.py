"""script.json 与 dev_store 合并测试。"""

import json

from core.models.entities import Project, Script
from core.store.memory import MemoryStore
from core.store.project_paths import ensure_project_layout, ensure_script_layout, sync_scripts_from_disk


def test_sync_scripts_from_disk_merges_longer_content_md(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "core.store.project_paths.PROJECTS_ROOT",
        tmp_path / "projects",
    )
    store = MemoryStore()
    project = Project(id="proj_a", title="P")
    store.add_project(project)
    script = Script(
        id="script_a",
        project_id=project.id,
        title="旧标题",
        content_md="短",
    )
    store.add_script(script)
    ensure_project_layout(project)
    disk_script = script.model_copy(
        update={
            "content_md": "# 完整剧本\n\n" + "正文" * 100,
            "title": "磁盘标题",
        }
    )
    ensure_script_layout(disk_script)

    changed = sync_scripts_from_disk(store)
    assert changed is True
    merged = store.get_script("script_a")
    assert merged is not None
    assert len(merged.content_md or "") > 10
    assert "完整剧本" in (merged.content_md or "")
