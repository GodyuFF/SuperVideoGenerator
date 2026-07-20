"""Agnes AI generate_images 集成测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from core.events.emitter import EventEmitter
from core.generation.queue import reset_generation_queue_for_tests
from core.llm.agent.react_core import AgentRunContext
from core.llm.agent.script_assets import create_text_asset_for_action
from core.llm.tools.image.generate import (
    collect_generation_items,
    run_concurrent_image_generation,
    slim_generate_images_args,
)
from core.llm.tools.image.handler import handle_generate_images
from core.llm.tools.image.settings import reset_image_gen_settings
from core.models.entities import Project, Script
from core.store import project_paths
from core.store.memory import MemoryStore
from tests.support.image_text_fixtures import prop_content


def _mock_http_image_download(monkeypatch, tmp_path):
    """将 HTTP 生图 URL 下载 mock 为本地 PNG 写入 tmp_path。"""
    monkeypatch.setattr(project_paths, "PROJECTS_ROOT", tmp_path)
    import base64

    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )

    def fake_download(url: str, dest, *, timeout: float = 120.0) -> str:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(png_bytes)
        return "image/png"

    monkeypatch.setattr("core.store.media_storage._download_http_to_file", fake_download)
    return png_bytes


@pytest.fixture(autouse=True)
def _reset_image_gen_settings():
    reset_image_gen_settings()
    yield
    reset_image_gen_settings()


@pytest.fixture(autouse=True)
def _reset_generation_queue():
    """隔离全局生成队列，避免跨用例串扰。"""
    reset_generation_queue_for_tests()
    yield
    reset_generation_queue_for_tests()


def _setup_prop_script():
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    asset = create_text_asset_for_action(
        store,
        action="create_prop",
        project_id=project.id,
        script_id=script.id,
        asset_name="道具",
        content=prop_content(
            summary="道具",
            description="测试道具，金属与木质混合，适合作为叙事中的小物件特写展示。",
        ),
        observation="",
    ).asset
    return store, script, project, asset


def test_collect_generation_items_from_scan():
    store, script, _, asset = _setup_prop_script()
    items = collect_generation_items(store, script.id, {"observation": "生图"})
    assert len(items) == 1
    assert items[0]["source_text_asset_id"] == asset.id
    assert items[0]["image_prompt"]


def test_slim_generate_images_args_strips_prompts():
    bloated = {
        "observation": "批量生图",
        "items": [
            {
                "asset_id": "txt_abc",
                "name": "老虎",
                "image_prompt": "a very long prompt " * 50,
            }
        ],
    }
    slim = slim_generate_images_args(bloated)
    assert slim["observation"] == "批量生图"
    assert slim["items"] == [{"source_text_asset_id": "txt_abc"}]
    assert "image_prompt" not in slim["items"][0]


@pytest.mark.asyncio
@patch("core.llm.tools.image.generate.generate_text_to_image_async", new_callable=AsyncMock)
async def test_run_concurrent_image_generation_calls_agnes(mock_generate, monkeypatch, tmp_path):
    mock_generate.return_value = "https://storage.agnes-ai.com/out.png"
    _mock_http_image_download(monkeypatch, tmp_path)
    store, script, project, asset = _setup_prop_script()
    ctx = AgentRunContext(
        task_brief="生图",
        work_context={"project_id": project.id, "script_id": script.id},
        script_id=script.id,
        step_id="step1",
        agent_name="image_agent",
    )
    with patch(
        "core.llm.tools.image.generate.is_image_gen_available",
        return_value=True,
    ):
        enriched, errors = await run_concurrent_image_generation(
            store,
            script.id,
            {"observation": "生图"},
            ctx,
        )
    assert not errors
    assert len(enriched["items"]) == 1
    assert enriched["items"][0]["url"].startswith(
        f"projects/{project.id}/scripts/{script.id}/assets/media/"
    )
    assert enriched["items"][0]["media_id"]
    mock_generate.assert_called_once()


@pytest.mark.asyncio
@patch("core.llm.tools.image.generate.generate_text_to_image_async", new_callable=AsyncMock)
async def test_run_concurrent_emits_progress_events(mock_generate, monkeypatch, tmp_path):
    mock_generate.return_value = "https://storage.agnes-ai.com/out.png"
    _mock_http_image_download(monkeypatch, tmp_path)
    store, script, project, asset = _setup_prop_script()
    emitter = EventEmitter()
    events: list[dict] = []

    async def capture(ev: dict) -> None:
        events.append(ev)

    emitter.subscribe(capture)
    ctx = AgentRunContext(
        task_brief="生图",
        work_context={
            "project_id": project.id,
            "script_id": script.id,
            "emitter": emitter,
        },
        script_id=script.id,
        step_id="step1",
        agent_name="image_agent",
    )
    with patch(
        "core.llm.tools.image.generate.is_image_gen_available",
        return_value=True,
    ):
        await run_concurrent_image_generation(
            store,
            script.id,
            {"observation": "生图"},
            ctx,
        )
    progress = [e for e in events if e.get("type") == "image_gen_progress"]
    assert len(progress) >= 2
    assert progress[0]["status"] == "started"
    assert any(e.get("status") == "completed" for e in progress)
    assert any(e.get("type") == "assets_changed" for e in events)


@pytest.mark.asyncio
@patch("core.llm.tools.image.generate.generate_text_to_image_async", new_callable=AsyncMock)
async def test_handle_generate_images_persists_media(mock_generate, monkeypatch, tmp_path):
    mock_generate.return_value = "https://storage.agnes-ai.com/out.png"
    _mock_http_image_download(monkeypatch, tmp_path)
    store, script, project, asset = _setup_prop_script()
    ctx = AgentRunContext(
        task_brief="生图",
        work_context={"project_id": project.id, "script_id": script.id},
        script_id=script.id,
        step_id="step1",
        agent_name="image_agent",
    )
    with patch(
        "core.llm.tools.image.generate.is_image_gen_available",
        return_value=True,
    ):
        result = await handle_generate_images(
            store,
            ctx,
            {"observation": "执行 generate_images"},
        )
    assert result.ok
    assert len(result.outputs) == 1
    updated = store.get_text_asset(asset.id)
    assert updated and updated.primary_media_id
    media = store.media_assets.get(updated.primary_media_id)
    assert media
    assert media.url.startswith(f"projects/{project.id}/scripts/{script.id}/assets/media/")
    assert media.metadata.get("source_url") == "https://storage.agnes-ai.com/out.png"
    disk_path = (
        tmp_path
        / project.id
        / "scripts"
        / script.id
        / "assets"
        / "media"
        / f"{media.id}.png"
    )
    assert disk_path.is_file()


@pytest.mark.asyncio
@patch("core.llm.tools.image.generate.generate_text_to_image_async", new_callable=AsyncMock)
async def test_generate_retries_three_times_then_aborts(mock_generate, monkeypatch, tmp_path):
    from core.llm.hook.react_guard import ImageGenerationAbortError
    from core.llm.tools.image.agnes_client import AgnesImageGenerationError

    mock_generate.side_effect = AgnesImageGenerationError("API 超时")
    store, script, project, _ = _setup_prop_script()
    ctx = AgentRunContext(
        task_brief="生图",
        work_context={"project_id": project.id, "script_id": script.id},
        script_id=script.id,
        step_id="step1",
        agent_name="image_agent",
    )
    with patch(
        "core.llm.tools.image.generate.is_image_gen_available",
        return_value=True,
    ):
        with pytest.raises(ImageGenerationAbortError) as exc_info:
            await run_concurrent_image_generation(
                store,
                script.id,
                {"observation": "生图"},
                ctx,
            )
    assert "在重试后仍失败" in str(exc_info.value)
    assert exc_info.value.failure_analysis is not None
    assert exc_info.value.failure_analysis.failed_count == 1
    assert mock_generate.call_count == 3


@pytest.mark.asyncio
@patch("core.llm.tools.image.generate.generate_text_to_image_async", new_callable=AsyncMock)
async def test_generate_succeeds_on_second_attempt(mock_generate, monkeypatch, tmp_path):
    from core.llm.tools.image.agnes_client import AgnesImageGenerationError

    mock_generate.side_effect = [
        AgnesImageGenerationError("临时失败"),
        "https://storage.agnes-ai.com/out.png",
    ]
    _mock_http_image_download(monkeypatch, tmp_path)
    store, script, project, _ = _setup_prop_script()
    ctx = AgentRunContext(
        task_brief="生图",
        work_context={"project_id": project.id, "script_id": script.id},
        script_id=script.id,
        step_id="step1",
        agent_name="image_agent",
    )
    with patch(
        "core.llm.tools.image.generate.is_image_gen_available",
        return_value=True,
    ):
        enriched, errors = await run_concurrent_image_generation(
            store,
            script.id,
            {"observation": "生图"},
            ctx,
        )
    assert not errors
    assert len(enriched["items"]) == 1
    assert mock_generate.call_count == 2


@pytest.mark.asyncio
async def test_enrich_skips_when_no_api_key():
    store, script, _, _ = _setup_prop_script()
    ctx = AgentRunContext(
        task_brief="",
        work_context={"script_id": script.id},
        script_id=script.id,
        step_id="",
        agent_name="image_agent",
    )
    with patch(
        "core.llm.tools.image.generate.is_image_gen_available",
        return_value=False,
    ):
        enriched, errors = await run_concurrent_image_generation(
            store,
            script.id,
            {"observation": "生图"},
            ctx,
        )
    assert errors == []
    assert "items" not in enriched
