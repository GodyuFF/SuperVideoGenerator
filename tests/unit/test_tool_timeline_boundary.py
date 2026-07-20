"""剪辑时间轴写入边界：非 editing_agent 不得侧效修改 edit_timelines。"""

from core.edit.shot_detail_sync import sync_actual_assets
from core.edit.timeline import compile_timeline_from_shots
from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.storyboard_refine.handler import handle_sync_actual_assets
from core.models.entities import MediaAsset, MediaAssetType
from core.store.memory import MemoryStore
from tests.support.shot_fixtures import _store_with_two_shots


def test_sync_actual_assets_does_not_modify_edit_timeline():
    """sync_actual_assets 仅写分镜计划稿，不创建或更新剪辑时间轴。"""
    store, script_id, shot1, shot2 = _store_with_two_shots()
    project_id = list(store.projects.keys())[0]
    plan = store.get_video_plan_for_script(script_id)
    assert plan
    assert store.get_edit_timeline_for_script(script_id) is None

    for shot, dur, text in (
        (shot1, 2500, "镜一"),
        (shot2, 4000, "镜二"),
    ):
        store.add_media_asset(
            MediaAsset(
                project_id=project_id,
                script_id=script_id,
                type=MediaAssetType.AUDIO,
                name=text,
                url=f"https://audio.test/{shot.id}.mp3",
                metadata={
                    "shot_id": shot.id,
                    "duration_ms": dur,
                    "subtitle_cues": [{"text": text, "start_ms": 0, "end_ms": dur}],
                },
            )
        )

    result = sync_actual_assets(store, script_id)
    assert "timeline_realigned" not in result
    assert store.get_edit_timeline_for_script(script_id) is None

    store.set_edit_timeline(compile_timeline_from_shots(store, script_id=script_id, plan=plan))
    timeline = store.get_edit_timeline_for_script(script_id)
    assert timeline is not None
    rev_before = timeline.revision

    result2 = sync_actual_assets(store, script_id)
    assert "timeline_realigned" not in result2
    timeline_after = store.get_edit_timeline_for_script(script_id)
    assert timeline_after is not None
    assert timeline_after.revision == rev_before


def _refine_ctx(store: MemoryStore, script_id: str) -> AgentRunContext:
    """构造分镜复核 Agent 测试上下文。"""
    return AgentRunContext(
        script_id=script_id,
        project_id=list(store.projects.keys())[0],
        task_brief="",
        work_context={},
        step_id="step_test",
        agent_name="storyboard_refine_agent",
        conversation_id="conv_test",
    )


def test_handle_sync_actual_assets_tool_boundary():
    """storyboard_refine Tool 包装层同样不得写剪辑时间轴。"""
    store, script_id, shot1, shot2 = _store_with_two_shots()
    project_id = list(store.projects.keys())[0]
    for shot, dur, text in ((shot1, 2500, "镜一"), (shot2, 4000, "镜二")):
        store.add_media_asset(
            MediaAsset(
                project_id=project_id,
                script_id=script_id,
                type=MediaAssetType.AUDIO,
                name=text,
                url=f"https://audio.test/{shot.id}.mp3",
                metadata={
                    "shot_id": shot.id,
                    "duration_ms": dur,
                    "subtitle_cues": [{"text": text, "start_ms": 0, "end_ms": dur}],
                },
            )
        )
    ctx = _refine_ctx(store, script_id)
    plan = store.get_video_plan_for_script(script_id)
    assert plan
    store.set_edit_timeline(compile_timeline_from_shots(store, script_id=script_id, plan=plan))
    before = store.get_edit_timeline_for_script(script_id)
    assert before is not None

    handle_sync_actual_assets(store, ctx, {"observation": "同步"})
    after = store.get_edit_timeline_for_script(script_id)
    assert after is not None
    assert after.revision == before.revision
