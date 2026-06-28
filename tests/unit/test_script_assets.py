"""剧本 Agent 文字资产 CRUD 与关联测试。"""

import pytest

from core.agents.llm_action import apply_action_result
from core.agents.react_core import AgentRunContext
from core.agents.script_assets import (
    create_text_asset_for_action,
    delete_text_asset_for_action,
    link_script_asset,
    list_script_asset_refs,
    update_text_asset_for_action,
)
from core.guards.reference import ReferenceGuardError
from core.models.entities import (
    AssetReference,
    AssetScope,
    MediaAsset,
    MediaAssetType,
    Project,
    RelationType,
    Script,
    TextAsset,
    TextAssetType,
)
from core.store.memory import MemoryStore


@pytest.fixture
def script_ctx() -> tuple[MemoryStore, str, str, AgentRunContext]:
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="第一集")
    store.add_script(script)
    ctx = AgentRunContext(
        task_brief="设计科幻短片",
        work_context={
            "project_id": project.id,
            "script_id": script.id,
            "user_message": "太空探险",
        },
        script_id=script.id,
        step_id="step1",
        agent_name="script_agent",
    )
    return store, project.id, script.id, ctx


def test_create_plot_links_to_script(script_ctx):
    store, _pid, script_id, _ctx = script_ctx
    plot = create_text_asset_for_action(
        store,
        action="create_plot",
        project_id=_pid,
        script_id=script_id,
        asset_name="开场",
        content={"text": "飞船起飞"},
        observation="",
    )
    refs = list_script_asset_refs(store, script_id)
    assert len(refs) == 1
    assert refs[0].target_id == plot.id
    assert refs[0].relation == RelationType.USES


def test_create_character_shared_and_linked(script_ctx):
    store, project_id, script_id, _ctx = script_ctx
    char = create_text_asset_for_action(
        store,
        action="create_character",
        project_id=project_id,
        script_id=script_id,
        asset_name="舰长",
        content={"appearance": "中年男性"},
        observation="",
    )
    assert char.scope == AssetScope.PROJECT_SHARED
    assert char.source_script_id == script_id
    assert any(r.target_id == char.id for r in list_script_asset_refs(store, script_id))


def test_update_plot_merges_content(script_ctx):
    store, _pid, script_id, _ctx = script_ctx
    plot = create_text_asset_for_action(
        store,
        action="create_plot",
        project_id=_pid,
        script_id=script_id,
        asset_name="段落1",
        content={"text": "初稿"},
        observation="",
    )
    updated = update_text_asset_for_action(
        store,
        action="update_plot",
        script_id=script_id,
        asset_id=plot.id,
        asset_name="段落1-修订",
        content={"text": "终稿"},
        observation="",
    )
    assert updated.name == "段落1-修订"
    assert updated.content["text"] == "终稿"


def test_delete_removes_asset_and_script_link(script_ctx):
    store, _pid, script_id, _ctx = script_ctx
    scene = create_text_asset_for_action(
        store,
        action="create_scene",
        project_id=_pid,
        script_id=script_id,
        asset_name="舰桥",
        content={"description": "金属走廊"},
        observation="",
    )
    delete_text_asset_for_action(
        store,
        action="delete_scene",
        script_id=script_id,
        asset_id=scene.id,
    )
    assert store.get_text_asset(scene.id) is None
    assert not list_script_asset_refs(store, script_id)


def test_delete_blocked_when_media_references(script_ctx):
    store, project_id, script_id, _ctx = script_ctx
    char = create_text_asset_for_action(
        store,
        action="create_character",
        project_id=project_id,
        script_id=script_id,
        asset_name="机器人",
        content={"appearance": "银色"},
        observation="",
    )
    store.add_reference(
        AssetReference(
            source_id="media_1",
            target_id=char.id,
            relation=RelationType.GENERATES,
            script_id=script_id,
        )
    )
    store.add_media_asset(
        MediaAsset(
            id="media_1",
            project_id=project_id,
            script_id=script_id,
            type=MediaAssetType.IMAGE,
            name="机器人图",
            source_asset_id=char.id,
        )
    )
    with pytest.raises(ReferenceGuardError):
        delete_text_asset_for_action(
            store,
            action="delete_character",
            script_id=script_id,
            asset_id=char.id,
        )


def test_apply_action_result_parse_brief(script_ctx):
    store, _pid, script_id, ctx = script_ctx
    obs = apply_action_result(
        store,
        "script_agent",
        "parse_brief",
        ctx,
        {"script_md": "# 标题\n\n正文", "observation": "完成"},
    )
    assert "完成" in obs
    script = store.get_script(script_id)
    assert script is not None
    assert "正文" in script.content_md


def test_apply_action_result_update_script(script_ctx):
    store, _pid, script_id, ctx = script_ctx
    apply_action_result(
        store,
        "script_agent",
        "update_script",
        ctx,
        {"title": "新标题", "script_md": "# 新标题\n\n新正文"},
    )
    script = store.get_script(script_id)
    assert script is not None
    assert script.title == "新标题"
    assert "新正文" in script.content_md
