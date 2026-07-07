"""主编排续跑意图与状态 JSON 测试。"""

import json

from core.llm.master.pipeline_progress import build_pipeline_progress
from core.llm.master.session import create_master_react_session
from core.llm.react_decide import build_master_react_state_json
from core.models.entities import GenerationMode, VideoStyleMode
from tests.unit.test_pipeline_progress import ready_for_edit_store


def test_master_state_includes_pipeline_progress(ready_for_edit_store):
    script_id = ready_for_edit_store._test_script_id  # type: ignore[attr-defined]
    progress = build_pipeline_progress(
        ready_for_edit_store, script_id, VideoStyleMode.DYNAMIC_IMAGE
    )
    session = create_master_react_session(
        conversation_id="conv_resume",
        project_id="p1",
        script_id=script_id,
        user_message="从剪辑合成继续",
        style_mode=VideoStyleMode.DYNAMIC_IMAGE,
        generation_mode=GenerationMode.AUTO,
    )
    session.extra["pipeline_progress"] = progress
    session.extra["user_resume_target"] = "edit_compose"
    state = json.loads(build_master_react_state_json(session))
    assert state["pipeline_progress"]["ready_for_edit_compose"] is True
    assert state["user_resume_target"] == "edit_compose"
    assert "storyboard" in state["pipeline_progress"]["inferred_completed_steps"]
    assert state["completed_actions"] == ["无"]
    assert "delegate_edit_compose" in state["available_actions"]
    assert "delegate_script_design" in state["available_actions"]
    assert state["next_actions"][0] == "delegate_edit_compose"


def test_new_conversation_does_not_seed_completed_from_store(ready_for_edit_store):
    """新对话：Store 已有全量素材时，completed_actions 仍为空，可重新委派。"""
    script_id = ready_for_edit_store._test_script_id  # type: ignore[attr-defined]
    progress = build_pipeline_progress(
        ready_for_edit_store, script_id, VideoStyleMode.DYNAMIC_IMAGE
    )
    session = create_master_react_session(
        conversation_id="conv_reedit",
        project_id="p1",
        script_id=script_id,
        user_message="重新剪辑视频，要求动物之间有互动，不要每张图都占满屏幕",
        style_mode=VideoStyleMode.DYNAMIC_IMAGE,
        generation_mode=GenerationMode.AUTO,
    )
    session.extra["pipeline_progress"] = progress
    session.extra["user_resume_target"] = "edit_compose"
    state = json.loads(build_master_react_state_json(session))
    assert state["completed_actions"] == ["无"]
    assert "delegate_edit_compose" in state["available_actions"]
    assert state["next_actions"][0] == "delegate_edit_compose"
    sub_completed = [s["completed"] for s in state["sub_agents"]]
    assert sub_completed == [False] * len(sub_completed)
