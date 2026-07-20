"""项目/剧本目录双写测试。"""

import json

from core.models.entities import Project, Script
from core.store.memory import MemoryStore
from core.store import project_paths
from core.store.media_storage import persist_media_url_to_disk
from core.store.persist import save_store


def test_ensure_project_and_script_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path)
    project = Project(title="测试项目")
    script = Script(project_id=project.id, title="第一集", duration_sec=90)

    project_paths.ensure_project_layout(project)
    project_paths.ensure_script_layout(script)

    assert (tmp_path / project.id / "project.json").is_file()
    assert (tmp_path / project.id / "scripts" / script.id / "script.json").is_file()
    assert (tmp_path / project.id / "scripts" / script.id / "assets" / "media").is_dir()

    proj_data = json.loads((tmp_path / project.id / "project.json").read_text(encoding="utf-8"))
    assert proj_data["title"] == "测试项目"


def test_save_store_syncs_meta(tmp_path, monkeypatch):
    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path)
    from core.store import persist

    monkeypatch.setattr(persist, "DEFAULT_PATH", tmp_path / "dev_store.json")
    monkeypatch.setattr(persist, "_ENABLED", True)

    store = MemoryStore()
    project = Project(title="P")
    store.add_project(project)
    script = Script(project_id=project.id, title="S")
    store.add_script(script)
    save_store(store, tmp_path / "dev_store.json")

    assert (tmp_path / project.id / "project.json").is_file()
    assert (tmp_path / project.id / "scripts" / script.id / "script.json").is_file()


def test_persist_media_data_url(tmp_path, monkeypatch):
    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path)
    import base64

    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    data_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
    rel = persist_media_url_to_disk(
        project_id="proj1",
        script_id="scr1",
        media_id="media1",
        url=data_url,
        media_type="image",
    )
    assert rel.startswith("projects/proj1/scripts/scr1/assets/media/media1.png")
    file_path = tmp_path / "proj1" / "scripts" / "scr1" / "assets" / "media" / "media1.png"
    assert file_path.is_file()
    assert file_path.read_bytes() == png_bytes


def test_persist_media_http_url(tmp_path, monkeypatch):
    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path)
    import base64

    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )

    class FakeResponse:
        content = png_bytes
        headers = {"content-type": "image/png"}

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url: str):
            assert url.startswith("https://")
            return FakeResponse()

    monkeypatch.setattr("core.store.media_storage.httpx.Client", FakeClient)

    rel = persist_media_url_to_disk(
        project_id="proj1",
        script_id="scr1",
        media_id="media2",
        url="https://storage.agnes-ai.com/out.png",
        media_type="image",
    )
    assert rel == "projects/proj1/scripts/scr1/assets/media/media2.png"
    file_path = tmp_path / "proj1" / "scripts" / "scr1" / "assets" / "media" / "media2.png"
    assert file_path.is_file()
    assert file_path.read_bytes() == png_bytes


def test_resolve_script_media_absolute_path_by_bare_media_id(tmp_path, monkeypatch):
    """裸 media_id（无扩展名）应能解析到落盘文件。"""
    from core.models.entities import AssetStatus, MediaAsset, MediaAssetType
    from core.store.media_storage import resolve_script_media_absolute_path

    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path)
    media_dir = project_paths.script_media_dir("proj1", "scr1")
    media_dir.mkdir(parents=True, exist_ok=True)
    (media_dir / "media_09bb5a381262.png").write_bytes(b"png")

    store = MemoryStore()
    store.media_assets["media_09bb5a381262"] = MediaAsset(
        id="media_09bb5a381262",
        project_id="proj1",
        script_id="scr1",
        name="测试图",
        type=MediaAssetType.IMAGE,
        status=AssetStatus.READY,
        url="projects/proj1/scripts/scr1/assets/media/media_09bb5a381262.png",
    )

    path = resolve_script_media_absolute_path(
        "proj1",
        "scr1",
        "media_09bb5a381262",
        store=store,
    )
    assert path is not None
    assert path.name == "media_09bb5a381262.png"
    assert path.is_file()


def test_discover_projects_from_disk_imports_missing_meta(tmp_path, monkeypatch):
    from core.store import persist

    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path)
    monkeypatch.setattr(persist, "DEFAULT_PATH", tmp_path / "dev_store.json")
    monkeypatch.setattr(persist, "_ENABLED", True)

    project = Project(title="磁盘项目")
    script = Script(project_id=project.id, title="第一集", duration_sec=60)
    project_paths.ensure_project_layout(project)
    project_paths.ensure_script_layout(script)

    store = MemoryStore()
    store.add_project(Project(title="已在内存"))
    assert project_paths.discover_projects_from_disk(store) is True
    assert store.get_project(project.id) is not None
    assert store.get_project(project.id).title == "磁盘项目"
    assert store.get_script(script.id) is not None


def test_discover_projects_from_disk_skips_existing(tmp_path, monkeypatch):
    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path)

    project = Project(title="已有")
    script = Script(project_id=project.id, title="S")
    project_paths.ensure_project_layout(project)
    project_paths.ensure_script_layout(script)

    store = MemoryStore()
    store.add_project(project)
    store.add_script(script)
    assert project_paths.discover_projects_from_disk(store) is False
