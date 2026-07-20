"""剧本 Agent 文字资产 CRUD 与关联测试。"""

import pytest

from core.llm.agent.llm_action import apply_action_result
from core.llm.agent.react_core import AgentRunContext
from core.llm.agent.script_assets import (
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
from tests.support.image_text_fixtures import character_content, scene_content


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
    ).asset
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
        content=character_content(
            summary="舰长",
            description="中年男性舰长，身着制服，神情沉稳，适合科幻叙事主角形象。",
            role="主角",
        ),
        observation="",
    ).asset
    assert char.scope == AssetScope.PROJECT_SHARED
    assert char.source_script_id == script_id
    assert "中年男性" in char.content["description"]
    assert str(char.content.get("tts_voice", "")).strip()
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
    ).asset
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
        content=scene_content(
            summary="舰桥",
            description="金属走廊与舰桥控制台，冷色灯光，科幻飞船内部场景，适合太空探险叙事。",
            location="舰桥",
        ),
        observation="",
    ).asset
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
        content=character_content(
            summary="机器人",
            description="银色金属外壳的服务机器人，流线型设计，适合科幻短片配角形象。",
            role="配角",
        ),
        observation="",
    ).asset
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
        {"content_md": "# 标题\n\n正文", "observation": "完成"},
    )
    assert "完成" in obs
    script = store.get_script(script_id)
    assert script is not None
    assert "正文" in script.content_md


def test_apply_action_result_update_script(script_ctx):
    """已确认标题不被 Agent update_script 覆盖，正文仍可更新。"""
    store, _pid, script_id, ctx = script_ctx
    apply_action_result(
        store,
        "script_agent",
        "update_script",
        ctx,
        {"title": "新标题", "content_md": "# 新标题\n\n新正文", "observation": "更新"},
    )
    script = store.get_script(script_id)
    assert script is not None
    assert script.title == "第一集"
    assert "新正文" in script.content_md


def test_apply_action_result_update_script_title_when_placeholder():
    """占位标题允许由 Agent 在剧本设计时写入正式名。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="默认剧本")
    store.add_script(script)
    ctx = AgentRunContext(
        task_brief="设计剧本",
        work_context={
            "project_id": project.id,
            "script_id": script.id,
            "user_message": "月光故事",
        },
        script_id=script.id,
        step_id="step1",
        agent_name="script_agent",
    )
    apply_action_result(
        store,
        "script_agent",
        "update_script",
        ctx,
        {"title": "月光下的约定", "content_md": "# 月光\n\n正文", "observation": "ok"},
    )
    updated = store.get_script(script.id)
    assert updated is not None
    assert updated.title == "月光下的约定"
