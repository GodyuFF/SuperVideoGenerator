"""list_images / media_list 单元测试。"""

import json

import pytest

from core.llm.agent.react_core import AgentRunContext
from core.llm.tools import get_tool_registry
from core.llm.tools.shared.executor import AgentToolExecutor
from core.llm.tools.shared.media_list import (
    build_media_item,
    build_media_list_payload,
    is_placeholder_media_url,
    resolve_media_access,
    resolve_media_duration_ms,
    resolve_media_play_link,
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


def test_build_media_item_includes_duration_ms_from_metadata():
    """metadata.duration_ms 应出现在 list 载荷中。"""
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.AUDIO,
        name="16s 音效",
        url="https://cdn.test/sfx.mp3",
        metadata={"duration_ms": 16000},
    )
    store.add_media_asset(media)
    item = build_media_item(store, media)
    assert item["duration_ms"] == 16000


def test_build_media_item_probes_local_audio(tmp_path, monkeypatch):
    """无 metadata 时应对本地 audio 文件探测 duration_ms。"""
    import wave

    from core.store import project_paths

    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path)
    media_dir = tmp_path / "p1" / "scripts" / "s1" / "assets" / "media"
    media_dir.mkdir(parents=True)
    wav_path = media_dir / "sfx.wav"
    with wave.open(str(wav_path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44100)
        handle.writeframes(b"\x00\x00" * 44100)

    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    rel = "projects/p1/scripts/s1/assets/media/sfx.wav"
    media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.AUDIO,
        name="本地音效",
        url=rel,
    )
    store.add_media_asset(media)
    item = build_media_item(store, media)
    assert item.get("duration_ms", 0) >= 900


def test_resolve_media_duration_ms_prefers_metadata():
    """resolve_media_duration_ms 应优先 metadata。"""
    media = MediaAsset(
        project_id="p",
        script_id="s",
        type=MediaAssetType.AUDIO,
        name="x",
        url="https://cdn.test/x.mp3",
        metadata={"duration_ms": 12345},
    )
    access = resolve_media_access(media.url)
    assert resolve_media_duration_ms(media, access) == 12345


def test_resolve_media_play_link_absolute_local_path(tmp_path, monkeypatch):
    """绝对本地路径应映射为 /api/ 播放链接，而非 file://。"""
    from core.store import project_paths

    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path)
    media_dir = tmp_path / "p1" / "scripts" / "s1" / "assets" / "media"
    media_dir.mkdir(parents=True)
    audio_path = media_dir / "media_abc.mp3"
    audio_path.write_bytes(b"\x00" * 256)

    media = MediaAsset(
        project_id="p1",
        script_id="s1",
        type=MediaAssetType.AUDIO,
        name="旁白",
        url=str(audio_path.resolve()),
    )
    link = resolve_media_play_link(media)
    assert link == "/api/projects/p1/scripts/s1/assets/media/media_abc.mp3"
    item = build_media_item(MemoryStore(), media)
    assert item["link"] == link
