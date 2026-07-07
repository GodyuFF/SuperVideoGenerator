"""timeline_service 单元测试。"""

import pytest

from core.edit.timeline_service import TimelineRevisionError, get_timeline_for_script, patch_timeline
from core.models.entities import Project, Script, ScriptStatus


@pytest.fixture
def store_with_script():
    from core.store.memory import MemoryStore

    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1", status=ScriptStatus.DRAFT)
    store.add_script(script)
    return store, project.id, script.id


def test_patch_timeline_creates_and_marks_user_edited(store_with_script):
    store, project_id, script_id = store_with_script
    view = patch_timeline(
        store,
        script_id=script_id,
        project_id=project_id,
        body={
            "tracks": {
                "video": [
                    {
                        "id": "clip_1",
                        "track": "video",
                        "start_ms": 0,
                        "end_ms": 3000,
                        "label": "镜1",
                    }
                ],
                "audio": [],
                "subtitle": [],
            }
        },
    )
    assert view["revision"] == 1
    assert view["user_edited"] is True
    assert view["last_edited_by"] == "user"
    assert len(view["tracks"]["video"]) == 1


def test_patch_timeline_revision_conflict(store_with_script):
    store, project_id, script_id = store_with_script
    patch_timeline(
        store,
        script_id=script_id,
        project_id=project_id,
        body={"tracks": {"video": [], "audio": [], "subtitle": []}},
    )
    with pytest.raises(TimelineRevisionError):
        patch_timeline(
            store,
            script_id=script_id,
            project_id=project_id,
            body={"tracks": {"video": [], "audio": [], "subtitle": []}},
            expected_revision=0,
        )


def test_get_timeline_for_script_none(store_with_script):
    store, _, script_id = store_with_script
    assert get_timeline_for_script(store, script_id) is None
