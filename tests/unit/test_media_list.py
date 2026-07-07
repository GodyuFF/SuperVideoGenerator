"""list_images / media_list 单元测试。"""

import json

import pytest

from core.llm.agent.react_core import AgentRunContext
from core.llm.tools import get_tool_registry
from core.llm.tools.shared.executor import AgentToolExecutor
from core.llm.tools.shared.media_list import (
    build_media_list_payload,
    is_placeholder_media_url,
    resolve_media_access,
)
from core.models.entities import (
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    TextAsset,
    TextAssetType,
)
from core.store.memory import MemoryStore


def test_is_placeholder_media_url():
    assert is_placeholder_media_url("")
    assert is_placeholder_media_url("/assets/demo.png")
    assert is_placeholder_media_url("timeline://etl_abc")
    assert not is_placeholder_media_url("https://cdn.test.org/a.png")


def test_resolve_media_access_http():
    info = resolve_media_access("https://cdn.test.org/img.png")
    assert info["link"] == "https://cdn.test.org/img.png"
    assert info["is_accessible"] is True
    assert info["file_path"] == ""


def test_resolve_media_access_project_relative(tmp_path, monkeypatch):
    from core.store import project_paths

    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path)
    media_dir = tmp_path / "p1" / "scripts" / "s1" / "assets" / "media"
    media_dir.mkdir(parents=True)
    (media_dir / "hero.png").write_bytes(b"png")

    rel = "projects/p1/scripts/s1/assets/media/hero.png"
    info = resolve_media_access(rel)
    assert info["link"] == "/api/projects/p1/scripts/s1/assets/media/hero.png"
    assert info["is_accessible"] is True
    assert info["file_path"].endswith("hero.png")


def test_build_media_list_payload_with_links():
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    char = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.CHARACTER,
        name="主角",
        content={"summary": "测试"},
    )
    store.add_text_asset(char)
    store.add_media_asset(
        MediaAsset(
            project_id=project.id,
            script_id=script.id,
            type=MediaAssetType.IMAGE,
            name="主角图",
            url="https://cdn.test/hero.png",
            source_asset_id=char.id,
            metadata={"generation_prompt": "a hero portrait, cinematic"},
        )
    )
    store.add_media_asset(
        MediaAsset(
            project_id=project.id,
            script_id=script.id,
            type=MediaAssetType.IMAGE,
            name="占位图",
            url="/assets/pending.png",
        )
    )

    payload = build_media_list_payload(store, script.id, MediaAssetType.IMAGE)
    assert payload["count"] == 2
    assert payload["accessible_count"] == 1

    hero = payload["items"][0]
    assert hero["link"] == "https://cdn.test/hero.png"
    assert hero["source_asset_name"] == "主角"
    assert hero["is_accessible"] is True
    assert "generation_prompt_preview" in hero

    pending = payload["items"][1]
    assert pending["is_placeholder"] is True
    assert pending["link"] == ""


@pytest.mark.asyncio
async def test_registry_list_images_returns_json_with_links():
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    store.add_media_asset(
        MediaAsset(
            project_id=project.id,
            script_id=script.id,
            type=MediaAssetType.IMAGE,
            name="场景图",
            url="https://static.test/scene.jpg",
        )
    )
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id},
        script_id=script.id,
        step_id="step1",
        agent_name="image_agent",
    )
    registry = get_tool_registry()
    result = await registry.call_tool(
        "list_images",
        {
            "observation": "列出图片",
            "plan_status": "列出已生成图片",
            "remaining_plan": ["finish"],
        },
        ctx,
        store,
    )
    assert result.ok
    assert result.structured["items"][0]["link"] == "https://static.test/scene.jpg"
    parsed = json.loads(result.observation)
    assert parsed["items"][0]["link"] == "https://static.test/scene.jpg"


def test_executor_list_images_summary():
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    store.add_media_asset(
        MediaAsset(
            project_id=project.id,
            script_id=script.id,
            type=MediaAssetType.IMAGE,
            name="场景图",
            url="https://static.test/scene.jpg",
        )
    )
    executor = AgentToolExecutor(store)
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id},
        script_id=script.id,
        step_id="step1",
        agent_name="image_agent",
    )
    text = executor.execute_by_action("image_agent", "list_images", ctx)
    assert "https://static.test/scene.jpg" in text
    assert "场景图" in text
