"""RAG 共享资产按需复用单元测试。"""

import pytest

from core.llm.agent.script_assets import (
    create_text_asset_for_action,
    link_script_asset,
    list_script_asset_refs,
)
from core.llm.tools.image.scan import build_scan_text_assets_payload
from core.llm.tools.script.list import build_text_assets_list_payload
from core.models.entities import (
    AssetScope,
    Project,
    RelationType,
    Script,
    TextAsset,
    TextAssetType,
)
from core.rag.indexer import upsert_asset_embedding_sync
from core.rag.resolver import resolve_shared_text_asset_sync
from core.rag.store import RagVectorStore
from core.store.memory import MemoryStore
from tests.support.image_text_fixtures import character_content, scene_content
from tests.support.rag_test_helpers import disable_project_rag
from tests.support.scripted_embedder import ScriptedEmbedder
from tests.support.scripted_reuse_judge import ScriptedReuseJudge


def _two_script_project() -> tuple[MemoryStore, str, str, str]:
    """双剧本项目。"""
    store = MemoryStore()
    project = Project(title="RAG 测试项目")
    store.add_project(project)
    script1 = Script(project_id=project.id, title="第一集", content_md="# 第一集\n林小雨日常")
    script2 = Script(project_id=project.id, title="第二集", content_md="# 第二集\n林小雨雨天")
    store.add_script(script1)
    store.add_script(script2)
    return store, project.id, script1.id, script2.id


def _index_character(
    store: MemoryStore,
    project_id: str,
    script_id: str,
    *,
    name: str = "林小雨",
    embedder: ScriptedEmbedder,
) -> TextAsset:
    """在 script1 创建并索引角色。"""
    content = character_content(
        summary="林小雨",
        description="二十出头女性，黑色长发，休闲装，温和气质，适合都市叙事主角形象描述扩展至足够长度满足校验规则。",
        role="主角",
    )
    char = TextAsset(
        project_id=project_id,
        type=TextAssetType.CHARACTER,
        name=name,
        content=content,
        scope=AssetScope.PROJECT_SHARED,
        source_script_id=script_id,
    )
    store.add_text_asset(char)
    link_script_asset(store, script_id, char.id)
    upsert_asset_embedding_sync(store, char, embedder=embedder)
    return char


def test_script2_isolated_before_rag_create():
    """未关联时 script2 的 list/scan 不含 script1 角色。"""
    store, project_id, script1_id, script2_id = _two_script_project()
    embedder = ScriptedEmbedder()
    _index_character(store, project_id, script1_id, embedder=embedder)

    assert store.list_assets_for_script(script2_id) == []
    payload = build_text_assets_list_payload(store, script2_id, include_content=False)
    types = {a["type"] for a in payload.get("assets", [])}
    assert "character" not in types

    scan = build_scan_text_assets_payload(store, script2_id)
    scan_ids = {a["id"] for a in scan.get("assets", [])}
    char = next(a for a in store.text_assets.values() if a.type == TextAssetType.CHARACTER)
    assert char.id not in scan_ids


def test_cross_script_rag_reuse():
    """script2 创建同名角色时 RAG reuse，不重复实体。"""
    store, project_id, script1_id, script2_id = _two_script_project()
    embedder = ScriptedEmbedder()
    original = _index_character(store, project_id, script1_id, embedder=embedder)
    judge = ScriptedReuseJudge(default="reuse")

    content = character_content(
        summary="林小雨",
        description="二十出头女性，黑色长发，休闲装，温和气质，适合都市叙事主角形象描述扩展至足够长度满足校验规则。",
        role="主角",
    )
    outcome = resolve_shared_text_asset_sync(
        store,
        action="create_character",
        project_id=project_id,
        script_id=script2_id,
        asset_name="林小雨",
        content=content,
        observation="",
        embedder=embedder,
        judge=judge,
    )

    assert outcome.rag_decision == "reuse"
    assert outcome.asset.id == original.id
    chars = [a for a in store.text_assets.values() if a.type == TextAssetType.CHARACTER]
    assert len(chars) == 1
    refs = list_script_asset_refs(store, script2_id)
    assert any(r.target_id == original.id and r.relation == RelationType.RAG_REUSE for r in refs)
    assert len(store.list_assets_for_script(script2_id)) == 1


def test_rag_fork_creates_variant():
    """相似场景 fork 产生新资产与 derived_from 边。"""
    store, project_id, script1_id, script2_id = _two_script_project()
    project = store.get_project(project_id)
    assert project is not None
    project.config.rag.similarity_threshold = -1.0
    embedder = ScriptedEmbedder()
    scene_content_base = scene_content(
        summary="普通咖啡厅",
        description="温馨木质装修的小型咖啡厅，暖色灯光，适合都市对话场景的背景描写扩展至足够长度满足系统校验。",
        location="咖啡厅",
    )
    original = TextAsset(
        project_id=project_id,
        type=TextAssetType.SCENE,
        name="普通咖啡厅",
        content=scene_content_base,
        scope=AssetScope.PROJECT_SHARED,
        source_script_id=script1_id,
    )
    store.add_text_asset(original)
    link_script_asset(store, script1_id, original.id)
    upsert_asset_embedding_sync(store, original, embedder=embedder)

    judge = ScriptedReuseJudge(
        decisions={
            "雨天咖啡厅": {
                "decision": "fork",
                "selected_asset_id": original.id,
                "fork_patch": {"summary": "雨天咖啡厅", "mood": "雨天"},
                "reason": "同地点不同天气",
            }
        }
    )
    new_content = scene_content(
        summary="雨天咖啡厅",
        description="雨天玻璃窗外的咖啡厅，冷色反光与暖色室内对比，适合第二集情绪转折的背景描写扩展至足够长度。",
        location="咖啡厅",
    )
    outcome = resolve_shared_text_asset_sync(
        store,
        action="create_scene",
        project_id=project_id,
        script_id=script2_id,
        asset_name="雨天咖啡厅",
        content=new_content,
        observation="",
        embedder=embedder,
        judge=judge,
    )
    assert outcome.rag_decision == "fork"
    assert outcome.asset.id != original.id
    derived = [
        r
        for r in store.references.values()
        if r.relation == RelationType.DERIVED_FROM
        and r.source_id == outcome.asset.id
        and r.target_id == original.id
    ]
    assert len(derived) == 1


def test_rag_create_new_when_no_candidates():
    """无候选时 create_new 并写入索引。"""
    store, project_id, _s1, script2_id = _two_script_project()
    embedder = ScriptedEmbedder()
    judge = ScriptedReuseJudge(default="create_new")
    content = character_content(
        summary="全新角色",
        description="从未出现过的配角形象，银框眼镜与实验室白大褂，适合科幻叙事扩展描写至足够长度满足校验。",
        role="配角",
    )
    outcome = resolve_shared_text_asset_sync(
        store,
        action="create_character",
        project_id=project_id,
        script_id=script2_id,
        asset_name="全新角色",
        content=content,
        observation="",
        embedder=embedder,
        judge=judge,
    )
    assert outcome.rag_decision == "create_new"
    assert RagVectorStore(project_id).get_hash(outcome.asset.id) is not None


def test_rag_disabled_always_creates_new():
    """rag.enabled=false 时跳过检索，直接新建。"""
    store, project_id, script1_id, script2_id = _two_script_project()
    disable_project_rag(store, project_id)
    embedder = ScriptedEmbedder()
    _index_character(store, project_id, script1_id, embedder=embedder)

    content = character_content(
        summary="林小雨",
        description="二十出头女性，黑色长发，休闲装，温和气质，适合都市叙事主角形象描述扩展至足够长度满足校验规则。",
        role="主角",
    )
    outcome = create_text_asset_for_action(
        store,
        action="create_character",
        project_id=project_id,
        script_id=script2_id,
        asset_name="林小雨",
        content=content,
        observation="",
    )
    assert outcome.rag_decision is None or outcome.rag_decision == "create_new"
    chars = [a for a in store.text_assets.values() if a.type == TextAssetType.CHARACTER]
    assert len(chars) == 2


def test_name_match_reuse_without_embedding(monkeypatch):
    """无 Embedding Key 时按规范化名称复用同名共享角色。"""
    from core.rag.settings import reset_embedding_manager

    reset_embedding_manager()
    monkeypatch.delenv("SVG_RAG_EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    store, project_id, script1_id, script2_id = _two_script_project()
    content = character_content(
        summary="林小雨",
        description="二十出头女性，黑色长发，休闲装，温和气质，适合都市叙事主角形象描述扩展至足够长度满足校验规则。",
        role="主角",
    )
    original = TextAsset(
        project_id=project_id,
        type=TextAssetType.CHARACTER,
        name="林小雨",
        content=content,
        scope=AssetScope.PROJECT_SHARED,
        source_script_id=script1_id,
    )
    store.add_text_asset(original)
    link_script_asset(store, script1_id, original.id)

    outcome = create_text_asset_for_action(
        store,
        action="create_character",
        project_id=project_id,
        script_id=script2_id,
        asset_name=" 林小雨 ",
        content=content,
        observation="",
    )
    assert outcome.rag_decision == "reuse"
    assert outcome.asset.id == original.id
    chars = [a for a in store.text_assets.values() if a.type == TextAssetType.CHARACTER]
    assert len(chars) == 1


def test_name_match_create_when_no_same_name(monkeypatch):
    """无 Embedding 且无同名资产时新建。"""
    from core.rag.settings import reset_embedding_manager

    reset_embedding_manager()
    monkeypatch.delenv("SVG_RAG_EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    store, project_id, script1_id, script2_id = _two_script_project()
    embedder = ScriptedEmbedder()
    _index_character(store, project_id, script1_id, name="林小雨", embedder=embedder)

    content = character_content(
        summary="夸父",
        description="神话巨人夸父，高大魁梧奔跑追日，适合神话叙事主角形象描述扩展至足够长度满足校验规则。",
        role="主角",
    )
    outcome = create_text_asset_for_action(
        store,
        action="create_character",
        project_id=project_id,
        script_id=script2_id,
        asset_name="夸父",
        content=content,
        observation="",
    )
    assert outcome.rag_decision == "create_new"
    assert outcome.asset.name == "夸父"


@pytest.mark.asyncio
async def test_create_character_inside_running_event_loop(monkeypatch):
    """FastAPI/ReAct 事件循环内同步创建角色不得抛「不可在运行中的事件循环内同步调用」。"""
    from core.rag.settings import reset_embedding_manager

    reset_embedding_manager()
    monkeypatch.delenv("SVG_RAG_EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    store, project_id, _script1_id, script2_id = _two_script_project()
    content = character_content(
        summary="橘猫团子",
        description="橙色短毛小猫，圆脸大眼，温顺好奇，适合温馨短片主角形象描述扩展至足够长度满足校验规则。",
        role="主角",
    )
    outcome = create_text_asset_for_action(
        store,
        action="create_character",
        project_id=project_id,
        script_id=script2_id,
        asset_name="橘猫团子",
        content=content,
        observation="创建主角小猫",
    )
    assert outcome.asset.name == "橘猫团子"
    assert outcome.asset.type == TextAssetType.CHARACTER
    assert outcome.asset.id in {
        r.target_id for r in list_script_asset_refs(store, script2_id)
    }


@pytest.mark.asyncio
async def test_vector_rag_reuse_inside_running_event_loop():
    """事件循环内带 ScriptedEmbedder 的向量 RAG reuse 应成功。"""
    store, project_id, script1_id, script2_id = _two_script_project()
    embedder = ScriptedEmbedder()
    original = _index_character(store, project_id, script1_id, embedder=embedder)
    judge = ScriptedReuseJudge(default="reuse")

    content = character_content(
        summary="林小雨",
        description="二十出头女性，黑色长发，休闲装，温和气质，适合都市叙事主角形象描述扩展至足够长度满足校验规则。",
        role="主角",
    )
    outcome = resolve_shared_text_asset_sync(
        store,
        action="create_character",
        project_id=project_id,
        script_id=script2_id,
        asset_name="林小雨",
        content=content,
        observation="",
        embedder=embedder,
        judge=judge,
    )
    assert outcome.rag_decision == "reuse"
    assert outcome.asset.id == original.id
