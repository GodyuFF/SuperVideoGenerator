"""资产谱系 REST API 集成测试。"""

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app
from apps.api.state import state
from core.llm.agent.script_assets import create_text_asset_for_action, link_script_asset
from core.models.entities import (
    AssetReference,
    MediaAsset,
    MediaAssetType,
    RelationType,
    ScriptStatus,
    VideoPlan,
    Shot,
)
from tests.support.image_text_fixtures import character_content


@pytest.mark.asyncio
async def test_get_asset_lineage_200():
    """存在资产时应返回 incoming/outgoing 谱系。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "谱系测试"})
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
        media = MediaAsset(
            project_id=pid,
            script_id=sid,
            type=MediaAssetType.IMAGE,
            name="小猫主图",
            url="/data/test.png",
            source_asset_id=char.id,
        )
        state.store.add_media_asset(media)
        state.store.add_reference(
            AssetReference(
                source_id=char.id,
                target_id=media.id,
                relation=RelationType.GENERATES,
                script_id=sid,
            )
        )

        r = await client.get(f"/api/projects/{pid}/assets/{char.id}/lineage")
        assert r.status_code == 200
        body = r.json()
        assert body["asset"]["id"] == char.id
        relations = {e["relation"] for e in body["outgoing"]}
        assert "generates" in relations


@pytest.mark.asyncio
async def test_get_asset_lineage_404():
    """未知资产 ID 应返回 404。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "谱系 404"})
        pid = r.json()["id"]
        r = await client.get(f"/api/projects/{pid}/assets/nonexistent-asset/lineage")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_script_graph_200():
    """剧本关系子图应返回 nodes/edges/stats。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "子图测试"})
        pid = r.json()["id"]
        r = await client.post(f"/api/projects/{pid}/scripts", json={"title": "S1"})
        sid = r.json()["id"]

        char = create_text_asset_for_action(
            state.store,
            action="create_character",
            project_id=pid,
            script_id=sid,
            asset_name="角色A",
            content=character_content(summary="角色A", description="角色描述。" * 10),
            observation="",
        ).asset
        from tests.support.shot_fixtures import make_shot

        shot = make_shot(order=0, text="旁白")
        shot.sub_shots[0] = shot.sub_shots[0].model_copy(
            update={"element_refs": {"character": [char.id]}}
        )
        state.store.set_video_plan(VideoPlan(script_id=sid, shots=[shot]))

        r = await client.get(f"/api/projects/{pid}/scripts/{sid}/graph")
        assert r.status_code == 200
        body = r.json()
        assert len(body["nodes"]) >= 2
        assert isinstance(body["edges"], list)
        assert "stats" in body


@pytest.mark.asyncio
async def test_delete_asset_blocked_returns_structured_references():
    """被其他剧本引用时删除应返回 409 与 references 边列表。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "删除守卫"})
        pid = r.json()["id"]
        r = await client.post(f"/api/projects/{pid}/scripts", json={"title": "S1"})
        sid1 = r.json()["id"]
        r = await client.post(f"/api/projects/{pid}/scripts", json={"title": "S2"})
        sid2 = r.json()["id"]

        char = create_text_asset_for_action(
            state.store,
            action="create_character",
            project_id=pid,
            script_id=sid1,
            asset_name="共享角色",
            content=character_content(summary="共享", description="共享角色描述。" * 10),
            observation="",
        ).asset
        link_script_asset(state.store, sid2, char.id)

        for script in state.store.scripts.values():
            if script.id in (sid1, sid2):
                script.status = ScriptStatus.COMPLETED

        r = await client.delete(f"/api/projects/{pid}/scripts/{sid1}/assets/{char.id}")
        assert r.status_code == 409
        body = r.json()
        detail = body["detail"]
        assert detail["asset_id"] == char.id
        assert isinstance(detail["references"], list)
        assert len(detail["references"]) >= 1
