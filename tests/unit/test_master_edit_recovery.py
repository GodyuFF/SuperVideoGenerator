"""剪辑缺失素材主编排恢复辅助函数与 compose 门禁测试。"""

import pytest

from core.edit.asset_resolver import EditTimelineValidationReport, MissingItem
from core.edit.timeline import normalize_tracks
from core.llm.agent.llm_action import apply_action_result
from core.llm.agent.react_core import AgentRunContext
from core.llm.hook.react_guard import EditComposeMissingAssetsError
from core.llm.master.edit_failure import (
    format_edit_compose_failure_observation,
    upstream_steps_to_redo,
    validation_report_from_structured,
)
from core.models.entities import EditTimeline, VideoStyleMode
from core.store.memory import MemoryStore
from tests.unit.test_edit_timeline_validation import store_with_plan


def test_upstream_steps_to_redo_deduplicates():
    items = [
        MissingItem(
            category="image",
            clip_id="c1",
            reason="缺图",
            suggested_upstream="image_gen",
        ),
        MissingItem(
            category="audio",
            clip_id="c2",
            reason="缺配音",
            suggested_upstream="tts_gen",
        ),
        MissingItem(
            category="image",
            clip_id="c3",
            reason="缺图2",
            suggested_upstream="image_gen",
        ),
    ]
    steps = upstream_steps_to_redo(items)
    assert steps == ["image_gen", "tts_gen"]


def test_format_edit_compose_failure_observation_includes_delegate_hints():
    report = EditTimelineValidationReport(
        ready=False,
        missing_items=[
            MissingItem(
                category="image",
                clip_id="clip_a",
                shot_id="shot_1",
                text_asset_id="txt_1",
                reason="视频轨片段缺少可访问图片",
                suggested_upstream="image_gen",
            )
        ],
    )
    obs = format_edit_compose_failure_observation(report)
    assert "【剪辑缺失明细】" in obs
    assert "delegate_agent" in obs
    assert "image_agent" in obs or "editing_agent" in obs
    assert "txt_1" in obs


def test_validation_report_from_structured_roundtrip():
    data = {
        "ready": False,
        "missing_items": [
            {
                "category": "audio",
                "clip_id": "a1",
                "reason": "缺配音",
                "suggested_upstream": "tts_gen",
            }
        ],
        "summary": {"missing_count": 1},
    }
    report = validation_report_from_structured(data)
    assert report is not None
    assert report.ready is False
    assert len(report.missing_items) == 1
    assert report.missing_items[0].suggested_upstream == "tts_gen"


def test_compose_final_raises_when_assets_missing(store_with_plan: MemoryStore):
    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    timeline = EditTimeline(
        script_id=script_id,
        duration_ms=5000,
        tracks=normalize_tracks(
            {
                "video": [
                    {
                        "track": "video",
                        "start_ms": 0,
                        "end_ms": 5000,
                        "asset_ref": "img_nonexistent",
                    }
                ],
                "audio": [],
                "subtitle": [],
            }
        ),
    )
    store_with_plan.set_edit_timeline(timeline)
    ctx = AgentRunContext(
        task_brief="合成",
        work_context={"style_mode": VideoStyleMode.STORYBOOK},
        script_id=script_id,
        step_id="edit_compose",
        agent_name="editing_agent",
        project_id=list(store_with_plan.projects.keys())[0],
    )
    with pytest.raises(EditComposeMissingAssetsError) as exc_info:
        apply_action_result(
            store_with_plan,
            "editing_agent",
            "compose_final",
            ctx,
            {"observation": ""},
        )
    assert exc_info.value.validation_report is not None
    assert exc_info.value.validation_report.ready is False
