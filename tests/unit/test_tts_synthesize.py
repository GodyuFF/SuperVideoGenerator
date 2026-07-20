"""TTS synthesize 落盘单元测试（mock 引擎）。"""

from unittest.mock import patch

import pytest

from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.tts.synthesize import (
    _resolve_synthesized_duration_ms,
    collect_narration_items,
    persist_single_synthesized_audio,
    run_concurrent_tts_synthesis,
)
from core.models.entities import MediaAssetType, VideoPlan, new_id
from core.store.memory import MemoryStore
from tests.support.fake_tts import fake_submaker_for_text, write_minimal_mp3
from tests.support.shot_fixtures import make_shot


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def tts_plan(store):
    script_id = "script_tts_syn"
    plan = VideoPlan(
        id=new_id("plan"),
        script_id=script_id,
        shots=[
            make_shot(order=0, duration_ms=3000, text="测试旁白一").model_copy(
                update={"id": "shot_1"}
            ),
        ],
    )
    store.video_plans[plan.id] = plan
    return script_id


def test_collect_narration_items(tts_plan, store):
    items = collect_narration_items(store, tts_plan, {})
    assert len(items) == 1
    assert items[0]["shot_id"] == "shot_1"


@pytest.mark.asyncio
async def test_run_concurrent_tts_synthesis_mock(tts_plan, store, tmp_path):
    ctx = AgentRunContext(
        task_brief="配音",
        work_context={"project_id": "proj_tts", "script_id": tts_plan},
        script_id=tts_plan,
        step_id="step_tts",
        agent_name="tts_agent",
    )

    def _fake_synthesize(text, voice_file, config, **kwargs):
        write_minimal_mp3(tmp_path / "dummy.mp3")
        import shutil

        shutil.copy(tmp_path / "dummy.mp3", voice_file)
        return fake_submaker_for_text(text, 2.5)

    with patch("core.llm.tools.tts.synthesize.synthesize_speech", side_effect=_fake_synthesize):
        with patch("core.llm.tools.tts.synthesize.get_tts_manager") as mock_mgr:
            mock_mgr.return_value.get_settings.return_value.enabled = True
            mock_mgr.return_value.get_settings.return_value.provider = "edge"
            mock_mgr.return_value.get_settings.return_value.max_concurrency = 2
            mock_mgr.return_value.resolved_api_key.return_value = None
            synthesized, obs = await run_concurrent_tts_synthesis(
                store, tts_plan, {"observation": "合成测试"}, ctx
            )
    assert len(synthesized) == 1
    assert "合成" in obs


def test_persist_single_synthesized_audio(tts_plan, store, tmp_path):
    out = tmp_path / "tts.mp3"
    write_minimal_mp3(out)
    ctx = AgentRunContext(
        task_brief="配音",
        work_context={"project_id": "proj_tts", "script_id": tts_plan},
        script_id=tts_plan,
        step_id="step_tts",
        agent_name="tts_agent",
    )
    media = persist_single_synthesized_audio(
        store,
        ctx,
        {
            "shot_id": "shot_1",
            "order": 0,
            "text": "测试旁白一",
            "url": str(out),
            "duration_ms": 2500,
            "subtitle_cues": [{"text": "测试旁白一", "start_ms": 0, "end_ms": 2500}],
        },
    )
    assert media is not None
    assert media.type == MediaAssetType.AUDIO
    assert media.metadata.get("shot_id") == "shot_1"


def test_resolve_synthesized_duration_ms_prefers_file(tmp_path):
    out = tmp_path / "a.mp3"
    write_minimal_mp3(out)
    sub = fake_submaker_for_text("hello", 1.0)
    duration_ms, drift_ms = _resolve_synthesized_duration_ms(out, sub)
    assert duration_ms > 0
