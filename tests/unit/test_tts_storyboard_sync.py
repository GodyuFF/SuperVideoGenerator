"""TTS synthesize 后自动同步分镜稿测试。"""

from unittest.mock import patch

import pytest

from core.edit.shot_detail_sync import sync_plan_from_tts
from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.tts.handler import handle_synthesize
from core.llm.tools.tts.synthesize import run_concurrent_tts_synthesis
from core.models.entities import VideoPlan, new_id
from core.store.memory import MemoryStore
from tests.support.fake_tts import fake_submaker_for_text, write_minimal_mp3
from tests.support.shot_fixtures import make_shot


@pytest.fixture
def tts_store() -> tuple[MemoryStore, str]:
    store = MemoryStore()
    script_id = "script_tts_board_sync"
    plan = VideoPlan(
        id=new_id("plan"),
        script_id=script_id,
        shots=[
            make_shot(order=0, duration_ms=3000, text="开场旁白").model_copy(
                update={"id": "shot_sync_1"}
            ),
        ],
    )
    store.video_plans[plan.id] = plan
    return store, script_id


@pytest.mark.asyncio
async def test_handle_synthesize_auto_syncs_shot_voice(tts_store, tmp_path, monkeypatch):
    """handle_synthesize 成功后应调用 sync_plan_from_tts 绑定镜内 voice clip。"""
    store, script_id = tts_store
    sync_calls: list[str] = []

    def _spy_sync(mem_store, sid: str):
        sync_calls.append(sid)
        return sync_plan_from_tts(mem_store, sid)

    monkeypatch.setattr("core.edit.shot_detail_sync.sync_plan_from_tts", _spy_sync)

    ctx = AgentRunContext(
        task_brief="配音",
        work_context={"project_id": "proj_tts", "script_id": script_id},
        script_id=script_id,
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
            synthesized, _ = await run_concurrent_tts_synthesis(
                store, script_id, {"observation": "合成"}, ctx
            )
    assert synthesized

    with patch(
        "core.llm.tools.tts.handler.run_concurrent_tts_synthesis",
        return_value=(synthesized, "已为 1 个镜头合成配音。"),
    ):
        result = await handle_synthesize(store, ctx, {"observation": "合成"})

    assert sync_calls == [script_id]
    assert result.ok
