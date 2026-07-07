"""用户手动增删改文字资产与剧本。"""

import pytest

from core.assets.user_crud import (
    assert_script_manually_editable,
    user_create_text_asset,
    user_delete_text_asset,
    user_patch_script,
)
from core.guards.reference import ScriptEditGuard, ScriptEditGuardError
from core.llm.agent.script_assets import create_text_asset_for_action
from core.models.entities import Project, Script, ScriptStatus
from core.store.memory import MemoryStore


@pytest.fixture
def ctx():
    store = MemoryStore()
    project = Project(title="P")
    store.add_project(project)
    script = Script(project_id=project.id, title="S", status=ScriptStatus.DRAFT)
    store.add_script(script)
    return store, project.id, script.id


def test_script_editable_includes_completed_and_failed():
    completed = Script(project_id="p1", title="t", status=ScriptStatus.COMPLETED)
    failed = Script(project_id="p1", title="t", status=ScriptStatus.FAILED)
    executing = Script(project_id="p1", title="t", status=ScriptStatus.EXECUTING)

    assert ScriptEditGuard.is_editable(completed)
    assert ScriptEditGuard.is_editable(failed)
    assert not ScriptEditGuard.is_editable(executing)


def test_user_create_and_delete_plot(ctx):
    store, pid, sid = ctx
    plot = user_create_text_asset(
        store,
        project_id=pid,
        script_id=sid,
        asset_type="plot",
        name="开场",
        content={"text": "故事从清晨开始。"},
    )
    assert plot.type.value == "plot"
    assert plot.user_edited is True
    assert store.list_assets_for_script(sid)

    user_delete_text_asset(store, project_id=pid, script_id=sid, asset_id=plot.id)
    assert store.get_text_asset(plot.id) is None


def test_user_create_character(ctx):
    store, pid, sid = ctx
    char = user_create_text_asset(
        store,
        project_id=pid,
        script_id=sid,
        asset_type="character",
        name="主角",
        content={"summary": "青年", "description": "穿风衣的青年走在雨夜街头，霓虹反射在湿润路面上。" * 3},
    )
    assert char.type.value == "character"
    assert char.content.get("image_prompt")


def test_block_edit_while_executing(ctx):
    store, pid, sid = ctx
    script = store.get_script(sid)
    assert script is not None
    script.status = ScriptStatus.EXECUTING

    with pytest.raises(ScriptEditGuardError):
        assert_script_manually_editable(store, sid)

    with pytest.raises(ScriptEditGuardError):
        user_create_text_asset(
            store,
            project_id=pid,
            script_id=sid,
            asset_type="plot",
            name="x",
            content={"text": "y"},
        )


def test_user_patch_script(ctx):
    store, pid, sid = ctx
    updated = user_patch_script(
        store,
        project_id=pid,
        script_id=sid,
        title="新标题",
        content_md="# 第一章\n\n正文。",
    )
    assert updated.title == "新标题"
    assert "第一章" in updated.content_md


def test_patch_blocked_when_linked_script_executing(ctx):
    store, pid, sid = ctx
    char = create_text_asset_for_action(
        store,
        action="create_character",
        project_id=pid,
        script_id=sid,
        asset_name="共享角色",
        content={
            "summary": "测试",
            "description": "测试角色描述" * 10,
            "prompt_hint": "侧光",
            "visual_style": "未指定",
            "color_palette": "未指定",
            "role": "主角",
            "personality": "未指定",
            "age_range": "未指定",
            "gender": "未指定",
            "costume": "未指定",
            "distinctive_features": "未指定",
            "ethnicity": "未指定",
            "body_type": "未指定",
            "height": "未指定",
            "build": "未指定",
            "hair_style": "未指定",
            "hair_color": "未指定",
            "eye_color": "未指定",
            "facial_features": "未指定",
            "default_expression": "未指定",
            "default_pose": "未指定",
            "accessories": "未指定",
        },
        observation="",
    )
    script = store.get_script(sid)
    assert script is not None
    script.status = ScriptStatus.EXECUTING

    from core.assets.user_crud import user_patch_text_asset

    with pytest.raises(ScriptEditGuardError):
        user_patch_text_asset(
            store,
            project_id=pid,
            asset_id=char.id,
            name="改名",
        )
