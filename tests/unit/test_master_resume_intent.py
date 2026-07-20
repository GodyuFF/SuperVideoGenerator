"""主编排续跑意图与状态 JSON 测试。"""

import json

from core.llm.master.pipeline_progress import (
    build_pipeline_progress,
    seed_completed_steps_for_message,
)
from core.llm.master.session import create_master_react_session
from core.llm.react_decide import build_master_react_state_json
from core.models.entities import GenerationMode, VideoStyleMode
from tests.unit.test_pipeline_progress import ready_for_edit_store


def test_master_state_includes_pipeline_progress(ready_for_edit_store):
    script_id = ready_for_edit_store._test_script_id  # type: ignore[attr-defined]
    progress = build_pipeline_progress(
        ready_for_edit_store, script_id, VideoStyleMode.STORYBOOK
    )
    session = create_master_react_session(
        conversation_id="conv_resume",
        project_id="p1",
        script_id=script_id,
        user_message="从剪辑合成继续",
        style_mode=VideoStyleMode.STORYBOOK,
        generation_mode=GenerationMode.AUTO,
    )
    seeded = seed_completed_steps_for_message(
        ready_for_edit_store,
        script_id,
        VideoStyleMode.STORYBOOK,
        "从剪辑合成继续",
    )
    session.completed_step_types = set(seeded)
    session.extra["pipeline_progress"] = progress
    session.extra["delegate_readiness"] = progress.get("delegate_readiness", [])
    session.extra["user_resume_target"] = "edit_compose"
    state = json.loads(build_master_react_state_json(session))
    assert state["pipeline_progress"]["ready_for_edit_compose"] is True
    assert state["user_resume_target"] == "edit_compose"
    assert "storyboard" in state["pipeline_progress"]["inferred_completed_steps"]
    assert "tts_gen" in seeded
    assert "edit_compose" not in seeded
    assert "step:tts_gen" in state["completed_actions"] or any(
        "tts" in a for a in state["completed_actions"]
    )
    assert "delegate_agent" in state["available_actions"]
    assert state["next_actions"][0] == "delegate_agent"


def test_seed_reuses_store_completed_unless_resume_or_full_redo(ready_for_edit_store):
    """新对话默认复用 Store 完成态；明确重做/续跑与全部重做除外。"""
    script_id = ready_for_edit_store._test_script_id  # type: ignore[attr-defined]
    plain = seed_completed_steps_for_message(
        ready_for_edit_store,
        script_id,
        VideoStyleMode.STORYBOOK,
        "看起来不错，可以再加上片尾字幕吗",
    )
    assert "tts_gen" in plain
    assert "storyboard" in plain

    resume_edit = seed_completed_steps_for_message(
        ready_for_edit_store,
        script_id,
        VideoStyleMode.STORYBOOK,
        "重新剪辑视频，要求动物之间有互动",
    )
    assert "tts_gen" in resume_edit
    assert "edit_compose" not in resume_edit

    redo_tts = seed_completed_steps_for_message(
        ready_for_edit_store,
        script_id,
        VideoStyleMode.STORYBOOK,
        "重新配音，语气更激昂一些",
    )
    assert "tts_gen" not in redo_tts
    assert "shot_detail" not in redo_tts
    assert "edit_compose" not in redo_tts

    # 普通提及「旁白」不应打开配音重做
    mention = seed_completed_steps_for_message(
        ready_for_edit_store,
        script_id,
        VideoStyleMode.STORYBOOK,
        "旁白感觉还行，先这样",
    )
    assert "tts_gen" in mention

    full = seed_completed_steps_for_message(
        ready_for_edit_store,
        script_id,
        VideoStyleMode.STORYBOOK,
        "推倒重来，全部重做",
    )
    assert full == set()


def test_seeded_session_marks_sub_agents_completed(ready_for_edit_store):
    """复用完成后，状态 JSON 中对应子 Agent completed=true。"""
    script_id = ready_for_edit_store._test_script_id  # type: ignore[attr-defined]
    progress = build_pipeline_progress(
        ready_for_edit_store, script_id, VideoStyleMode.STORYBOOK
    )
    session = create_master_react_session(
        conversation_id="conv_reuse",
        project_id="p1",
        script_id=script_id,
        user_message="继续完善一下成片",
        style_mode=VideoStyleMode.STORYBOOK,
        generation_mode=GenerationMode.AUTO,
    )
    seeded = seed_completed_steps_for_message(
        ready_for_edit_store,
        script_id,
        VideoStyleMode.STORYBOOK,
        "继续完善一下成片",
    )
    session.completed_step_types = set(seeded)
    session.extra["pipeline_progress"] = progress
    session.extra["delegate_readiness"] = progress.get("delegate_readiness", [])
    state = json.loads(build_master_react_state_json(session))
    by_id = {s["agent_id"]: s for s in state["sub_agents"]}
    assert by_id.get("tts_agent", {}).get("completed") is True
    assert "tts_agent" not in state.get("available_sub_agents", [])
