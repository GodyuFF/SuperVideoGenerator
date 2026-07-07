"""项目/剧本删除与级联清理测试。"""

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app
from apps.api.state import create_project, create_script, state
from core.conversation.index import ConversationIndex
from core.conversation.store import ConversationStore
from core.conversation.sqlite_store import ConversationSqliteStore
from core.models.entities import Project, Script, TextAsset, TextAssetType
from core.store import project_paths
from core.store.memory import MemoryStore
from core.store.persist import save_store


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    """独立 MemoryStore + 项目目录，避免污染全局 state。"""
    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path)
    from core.store import persist

    store_path = tmp_path / "dev_store.json"
    monkeypatch.setattr(persist, "DEFAULT_PATH", store_path)
    monkeypatch.setattr(persist, "_ENABLED", True)

    store = MemoryStore()
    project = Project(title="删除测试")
    store.add_project(project)
    script = Script(project_id=project.id, title="第一集")
    store.add_script(script)
    asset = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.PLOT,
        name="情节",
        content={"summary": "测试"},
    )
    store.add_text_asset(asset)
    project_paths.ensure_project_layout(project)
    project_paths.ensure_script_layout(script)
    save_store(store, store_path)
    return store, project, script, store_path


def test_memory_store_delete_script_cascade(isolated_store):
    store, project, script, _ = isolated_store
    assert store.delete_script(script.id) is True
    assert store.get_script(script.id) is None
    assert not store.list_assets_for_script(script.id)
    assert project.id in store.projects


def test_memory_store_delete_project_cascade(isolated_store):
    store, project, script, _ = isolated_store
    assert store.delete_project(project.id) is True
    assert store.get_project(project.id) is None
    assert not store.list_scripts_for_project(project.id)


def test_remove_project_dir(isolated_store, tmp_path):
    _, project, script, _ = isolated_store
    media_dir = (
        tmp_path
        / project.id
        / "scripts"
        / script.id
        / "assets"
        / "media"
    )
    media_dir.mkdir(parents=True, exist_ok=True)
    (media_dir / "test.png").write_bytes(b"png")

    project_paths.remove_script_dir(project.id, script.id)
    assert not project_paths.script_dir(project.id, script.id).exists()

    project_paths.remove_project_dir(project.id)
    assert not project_paths.project_dir(project.id).exists()


def test_conversation_sqlite_delete_by_script(tmp_path):
    db_path = tmp_path / "conversations.db"
    sqlite = ConversationSqliteStore(db_path)
    index = ConversationIndex()
    conv = index.create("proj1", "scr1", title="对话1")
    sqlite.upsert_conversation(conv)
    store = ConversationStore(sqlite_store=sqlite)
    store.add_user_message(conv.id, "proj1", "scr1", "你好")

    sqlite.delete_by_script_id("proj1", "scr1")
    index.delete_by_script_id("proj1", "scr1")
    store.delete_by_script_id("proj1", "scr1")

    assert index.get(conv.id) is None
    assert sqlite.message_count() == 0


@pytest.mark.asyncio
async def test_api_delete_project_and_script(monkeypatch, tmp_path):
    from core.store import persist

    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path)
    store_path = tmp_path / "dev_store.json"
    monkeypatch.setattr(persist, "DEFAULT_PATH", store_path)
    monkeypatch.setattr(persist, "_ENABLED", True)
    db_path = tmp_path / "conversations.db"
    monkeypatch.setattr(
        "core.conversation.sqlite_store.DEFAULT_DB_PATH",
        db_path,
    )

    state.store.clear()
    state.conversation_index.clear()
    state.conversations.clear()
    state.conversation_sqlite = ConversationSqliteStore(db_path)

    project = create_project("API 删除测试")
    script = create_script(project.id, "剧本 A")
    conv = state.conversation_index.create(project.id, script.id)
    state.conversations.add_user_message(conv.id, project.id, script.id, "测试")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.delete(f"/api/projects/{project.id}/scripts/{script.id}")
        assert r.status_code == 200
        assert state.store.get_script(script.id) is None
        assert not project_paths.script_dir(project.id, script.id).exists()

        r = await client.delete(f"/api/projects/{project.id}")
        assert r.status_code == 200
        assert state.store.get_project(project.id) is None
        assert not project_paths.project_dir(project.id).exists()

        r = await client.post(
            "/api/projects/batch-delete",
            json={"project_ids": ["proj_missing"]},
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_orphan_project_dir_only(monkeypatch, tmp_path):
    """仅磁盘存在 project 目录时，DELETE 应清理目录。"""
    from core.store import persist

    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path)
    monkeypatch.setattr(project_paths, "DATA_ROOT", tmp_path)
    store_path = tmp_path / "dev_store.json"
    monkeypatch.setattr(persist, "DEFAULT_PATH", store_path)
    monkeypatch.setattr(persist, "_ENABLED", True)

    orphan = Project(title="孤儿项目")
    project_paths.ensure_project_layout(orphan)
    assert (tmp_path / orphan.id).is_dir()

    state.store.clear()
    assert state.store.get_project(orphan.id) is None

    from apps.api.state import delete_project

    delete_project(orphan.id)
    assert not project_paths.project_dir(orphan.id).exists()


@pytest.mark.asyncio
async def test_create_project_does_not_wipe_existing(monkeypatch, tmp_path):
    from core.store import persist

    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path)
    store_path = tmp_path / "dev_store.json"
    monkeypatch.setattr(persist, "DEFAULT_PATH", store_path)
    monkeypatch.setattr(persist, "_ENABLED", True)

    state.store.clear()
    p1 = create_project("项目一")
    p2 = create_project("项目二")
    assert state.store.get_project(p1.id) is not None
    assert state.store.get_project(p2.id) is not None
    assert len(state.store.projects) == 2
