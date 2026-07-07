"""scan_text_assets JSON 载荷测试。"""

import json

import pytest

from core.llm.agent.react_core import AgentRunContext
from core.llm.agent.script_assets import create_text_asset_for_action
from core.llm.tools.image.scan import build_scan_text_assets_payload
from core.llm.tools.shared.executor import AgentToolExecutor
from core.llm.tools import get_tool_registry
from core.models.entities import Project, Script
from core.store.memory import MemoryStore
from tests.support.image_text_fixtures import prop_content


def _setup_prop_script():
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    create_text_asset_for_action(
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
    )
    return store, script, project


def test_scan_text_assets_payload_json():
    store, script, project = _setup_prop_script()
    payload = build_scan_text_assets_payload(store, script.id)
    assert payload["project_id"] == project.id
    assert payload["project_title"] == project.title
    assert payload["script"]["id"] == script.id
    assert payload["count"] == 1
    assert payload["pending_count"] == 1
    assert payload["counts_by_type"]["prop"] == 1
    asset = payload["assets"][0]
    assert asset["type"] == "prop"
    assert asset["has_image_prompt"] is True
    assert asset["needs_generation"] is True
    assert asset["image_status"] == "missing"
    assert asset["linked_media"] == []
    assert asset["linked_media_count"] == 0


def test_scan_text_assets_executor_returns_json():
    store, script, _ = _setup_prop_script()
    raw = AgentToolExecutor.scan_summary(store, script.id)
    data = json.loads(raw)
    assert data["count"] == 1
    assert "script" in data
    assert "道具" in data["assets"][0]["name"]


def test_scan_text_assets_includes_prop():
    store, script, _ = _setup_prop_script()
    summary = AgentToolExecutor.scan_summary(store, script.id)
    parsed = json.loads(summary)
    assert parsed["counts_by_type"]["prop"] == 1
    assert "道具" in parsed["assets"][0]["name"]


@pytest.mark.asyncio
async def test_registry_scan_text_assets_structured_payload():
    store, script, project = _setup_prop_script()
    ctx = AgentRunContext(
        task_brief="扫描",
        work_context={"project_id": project.id, "script_id": script.id},
        script_id=script.id,
        step_id="step1",
        agent_name="image_agent",
    )
    registry = get_tool_registry()
    result = await registry.call_tool(
        "scan_text_assets",
        {"observation": "开始扫描待生图的文字资产"},
        ctx,
        store,
    )
    assert result.ok, result.observation
    assert "action" not in result.structured
    assert "summary" not in result.structured
    assert result.structured["project_id"] == project.id
    assert result.structured["script_id"] == script.id
    assert result.structured["count"] == 1
    assert json.loads(result.observation.split("\n\n")[-1])["count"] == 1 or json.loads(
        result.observation
    )["count"] == 1
