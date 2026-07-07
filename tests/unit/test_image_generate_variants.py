"""变体粒度 scan / generate / persist 测试。"""

from unittest.mock import patch

import pytest

from core.llm.agent.llm_action import persist_single_generated_image
from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.image.scan import build_scan_text_assets_payload
from core.llm.tools.image.variants import collect_variant_generation_items
from core.models.entities import (
    AssetScope,
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    TextAsset,
    TextAssetType,
)
from core.models.image_text_asset import merge_incoming_variants, normalize_image_text_content, parse_image_variants
from core.store.memory import MemoryStore
from tests.support.image_text_fixtures import character_content


@pytest.fixture
def variant_store() -> MemoryStore:
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    raw = character_content(summary="主角")
    content = normalize_image_text_content(TextAssetType.CHARACTER, raw)
    content = merge_incoming_variants(
        content,
        [
            {
                "kind": "expression",
                "label": "微笑",
                "meaning": "开场",
                "variant_prompt": "温和微笑",
            }
        ],
    )
    char = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="主角",
        content=content,
    )
    store.add_text_asset(char)
    store._test_script_id = script.id  # type: ignore[attr-defined]
    store._test_project_id = project.id  # type: ignore[attr-defined]
    store._test_char_id = char.id  # type: ignore[attr-defined]
    return store


def test_scan_reports_pending_variants(variant_store: MemoryStore):
    script_id = variant_store._test_script_id  # type: ignore[attr-defined]
    payload = build_scan_text_assets_payload(variant_store, script_id)
    asset = payload["assets"][0]
    assert asset["pending_variant_count"] >= 2
    assert len(asset["variants"]) >= 2
    assert asset["needs_generation"] is True


def test_collect_variant_items_base_before_derivative(variant_store: MemoryStore):
    script_id = variant_store._test_script_id  # type: ignore[attr-defined]
    items = collect_variant_generation_items(variant_store, script_id)
    assert len(items) >= 1
    assert items[0]["variant_kind"] == "base"
    # 无 base 图时衍生变体不入队
    assert all(i.get("variant_kind") == "base" for i in items)


def test_persist_base_sets_primary_derivative_does_not(variant_store: MemoryStore):
    script_id = variant_store._test_script_id  # type: ignore[attr-defined]
    project_id = variant_store._test_project_id  # type: ignore[attr-defined]
    char_id = variant_store._test_char_id  # type: ignore[attr-defined]
    items = collect_variant_generation_items(variant_store, script_id)
    base_item = items[0]
    ctx = AgentRunContext(
        task_brief="",
        work_context={"script_id": script_id, "project_id": project_id},
        script_id=script_id,
        step_id="image_gen",
        agent_name="image_agent",
        project_id=project_id,
    )

    def _fake_persist(**kwargs):
        return kwargs["url"]

    with patch(
        "core.store.media_storage.persist_media_url_to_disk",
        side_effect=_fake_persist,
    ):
        persist_single_generated_image(
            variant_store,
            ctx,
            {**base_item, "url": "https://images.test/base.png"},
        )
        char = variant_store.get_text_asset(char_id)
        assert char
        primary_after_base = char.primary_media_id

        deriv = {
            **base_item,
            "variant_id": [
                v.id for v in parse_image_variants(char.content) if v.kind == "expression"
            ][0],
            "variant_kind": "expression",
            "name": "主角-微笑",
        }
        persist_single_generated_image(
            variant_store,
            ctx,
            {**deriv, "url": "https://images.test/smile.png"},
        )

    char = variant_store.get_text_asset(char_id)
    assert char
    assert char.primary_media_id == primary_after_base
    linked = [
        m
        for m in variant_store.media_assets.values()
        if m.source_asset_id == char_id
    ]
    assert len(linked) == 2
