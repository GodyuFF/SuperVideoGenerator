"""实际生成提示词预览：领域层与 API。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app
from apps.api.state import state
from core.assets.resolved_prompt import (
    ResolvedPromptNotFoundError,
    ResolvedPromptUnsupportedError,
    build_resolved_prompt,
)
from core.llm.agent.script_assets import create_text_asset_for_action
from core.models.entities import (
    AssetScope,
    Project,
    Script,
    TextAsset,
    TextAssetType,
)
from core.store.memory import MemoryStore
from tests.support.image_text_fixtures import character_content


def _store_with_frame() -> tuple[MemoryStore, str, str]:
    """构建含 frame + 关联角色/空镜的 store，返回 (store, project_id, frame_id)。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    scene = TextAsset(
        project_id=project.id,
        type=TextAssetType.SCENE,
        scope=AssetScope.PROJECT_SHARED,
        name="夕阳蜂巢入口",
        content={"summary": "橙金色蜂巢入口", "description": "巨大六角蜂巢"},
        source_script_id=script.id,
    )
    character = TextAsset(
        project_id=project.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.PROJECT_SHARED,
        name="女娲",
        content={
            "summary": "创世女神",
            "description": "长发女神",
            "costume": "绯色长袍",
        },
        source_script_id=script.id,
    )
    store.add_text_asset(scene)
    store.add_text_asset(character)
    frame = TextAsset(
        project_id=project.id,
        type=TextAssetType.FRAME,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="飞入",
        content={
            "summary": "飞入蜂巢",
            "image_prompt": "女娲飞入蜂巢",
            "element_refs": {"scene": [scene.id], "character": [character.id]},
        },
        source_script_id=script.id,
    )
    store.add_text_asset(frame)
    return store, project.id, frame.id


def test_build_resolved_prompt_frame_includes_linked_context():
    """frame 实际生成提示词应含关联资产上下文与角色名。"""
    store, pid, frame_id = _store_with_frame()
    result = build_resolved_prompt(store, pid, frame_id)
    assert result["asset_type"] == "frame"
    assert result["kind"] == "image"
    assert result["authored_prompt"] == "女娲飞入蜂巢"
    assert "【关联资产上下文】" in result["resolved_prompt"]
    assert "女娲" in result["resolved_prompt"]
    assert result["differs_from_authored"] is True


def test_build_resolved_prompt_no_refs_differs_false():
    """无 element_refs 时 authored 与 resolved 通常一致。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    frame = TextAsset(
        project_id=project.id,
        type=TextAssetType.FRAME,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="空镜画面",
        content={
            "summary": "空",
            "image_prompt": "只有背景的空旷山谷",
            "element_refs": {},
        },
        source_script_id=script.id,
    )
    store.add_text_asset(frame)
    result = build_resolved_prompt(store, project.id, frame.id)
    assert result["resolved_prompt"] == result["authored_prompt"]
    assert result["differs_from_authored"] is False


def test_build_resolved_prompt_not_found():
    """未知资产应抛 ResolvedPromptNotFoundError。"""
    store = MemoryStore()
    store.add_project(Project(title="p", id="proj_x"))
    with pytest.raises(ResolvedPromptNotFoundError):
        build_resolved_prompt(store, "proj_x", "text_missing")


def test_build_resolved_prompt_unsupported_plot():
    """剧情等类型应抛 Unsupported。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    plot = TextAsset(
        project_id=project.id,
        type=TextAssetType.PLOT,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="剧情",
        content={"body": "正文"},
        source_script_id=script.id,
    )
    store.add_text_asset(plot)
    with pytest.raises(ResolvedPromptUnsupportedError):
        build_resolved_prompt(store, project.id, plot.id)


@pytest.mark.asyncio
async def test_get_resolved_prompt_api_200():
    """GET resolved-prompt 应返回完整字段。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "提示词预览"})
        pid = r.json()["id"]
        r = await client.post(f"/api/projects/{pid}/scripts", json={"title": "S1"})
        sid = r.json()["id"]
        char = create_text_asset_for_action(
            state.store,
            action="create_character",
            project_id=pid,
            script_id=sid,
            asset_name="小猫",
            content=character_content(summary="小猫", description="一只橘色小猫。" * 10),
            observation="",
        ).asset
        r = await client.get(f"/api/projects/{pid}/assets/{char.id}/resolved-prompt")
        assert r.status_code == 200
        body = r.json()
        assert body["asset_id"] == char.id
        assert body["asset_type"] == "character"
        assert body["kind"] == "image"
        assert "authored_prompt" in body
        assert "resolved_prompt" in body
        assert isinstance(body["differs_from_authored"], bool)


@pytest.mark.asyncio
async def test_get_resolved_prompt_api_404():
    """未知资产应 404。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "提示词 404"})
        pid = r.json()["id"]
        r = await client.get(f"/api/projects/{pid}/assets/nonexistent/resolved-prompt")
        assert r.status_code == 404
