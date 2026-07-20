"""delegate_agent 工具与会话状态组装测试。"""

import json

from core.llm.master.delegate_tool import (
    build_delegate_agent_description,
    build_delegate_agent_input_schema,
    build_sub_agents_orchestration_state,
    eligible_agent_ids_from_readiness,
)
from core.llm.master.session import create_master_react_session
from core.llm.react_decide import build_master_react_state_json
from core.models.entities import GenerationMode, VideoStyleMode


def test_eligible_agent_ids_from_readiness_skips_completed_and_hard_block():
    readiness = [
        {
            "agent_id": "script_agent",
            "step_type": "script_design",
            "ready": True,
            "soft_blockers": [],
            "hard_blockers": [],
        },
        {
            "agent_id": "video_agent",
            "step_type": "video_gen",
            "ready": False,
            "soft_blockers": [],
            "hard_blockers": ["当前风格不可委派 video_gen"],
        },
    ]
    ids = eligible_agent_ids_from_readiness(readiness, {"script_design"})
    assert ids == []


def test_build_sub_agents_orchestration_state_marks_available():
    readiness = [
        {
            "agent_id": "script_agent",
            "step_type": "script_design",
            "ready": True,
            "soft_blockers": [],
            "hard_blockers": [],
        },
        {
            "agent_id": "image_agent",
            "step_type": "image_gen",
            "ready": False,
            "soft_blockers": ["建议先完成剧本"],
            "hard_blockers": [],
        },
    ]
    rows, available = build_sub_agents_orchestration_state(
        profile_id="default",
        style_mode=VideoStyleMode.STORYBOOK,
        completed_step_types=set(),
        delegate_readiness=readiness,
    )
    script_row = next(r for r in rows if r["agent_id"] == "script_agent")
    assert script_row["available"] is True
    assert script_row["description"]
    assert "script_agent" in available


def test_delegate_tool_schema_enum_uses_eligible_ids():
    schema = build_delegate_agent_input_schema(
        "default",
        VideoStyleMode.STORYBOOK,
        eligible_agent_ids=["script_agent"],
    )
    enum_ids = schema["properties"]["agent_id"]["enum"]
    assert enum_ids == ["script_agent"]
    assert "image_agent" not in enum_ids


def test_delegate_tool_description_lists_current_eligible():
    desc = build_delegate_agent_description(
        "default",
        VideoStyleMode.STORYBOOK,
        eligible_agent_ids=["script_agent"],
        delegate_readiness=[
            {
                "agent_id": "script_agent",
                "step_type": "script_design",
                "ready": True,
                "soft_blockers": [],
                "hard_blockers": [],
            }
        ],
    )
    assert "当前可委派 agent_id：script_agent" in desc
    assert "【本轮可委派】" in desc
    assert "必须单独成轮" in desc


def test_master_state_json_includes_available_sub_agents():
    session = create_master_react_session(
        conversation_id="conv_avail",
        project_id="p1",
        script_id="s1",
        user_message="测试",
        style_mode=VideoStyleMode.STORYBOOK,
        generation_mode=GenerationMode.AUTO,
    )
    session.extra["delegate_readiness"] = [
        {
            "agent_id": "script_agent",
            "step_type": "script_design",
            "ready": True,
            "soft_blockers": [],
            "hard_blockers": [],
        }
    ]
    state = json.loads(build_master_react_state_json(session))
    assert "available_sub_agents" in state
    assert "script_agent" in state["available_sub_agents"]
    assert state["sub_agents"][0]["description"]
