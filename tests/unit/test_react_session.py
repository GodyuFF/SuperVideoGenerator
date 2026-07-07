"""单元测试：ReActSession 与主编排工具。"""

import json

import pytest

from core.conversation import ConversationStore
from core.llm.client import LLMClient
from core.llm.model import new_conversation_id
from core.llm.react_decide import (
    build_master_react_state_json,
    build_master_react_system,
    decide_master_session,
)
from core.llm.client.settings import LLMConfigManager
from core.models.entities import GenerationMode, VideoStyleMode
from core.llm.master import MasterToolExecutor, create_master_react_session
from core.llm.prompt.chat_messages import MASTER_STATE_HEADER, extract_master_state_json
from core.store.memory import MemoryStore
from tests.support.scripted_llm import ScriptedLLMClient


def test_new_conversation_id_prefix():
    cid = new_conversation_id()
    assert cid.startswith("conv_")


def test_react_session_available_actions_include_tools_and_delegates():
    session = create_master_react_session(
        conversation_id="conv_test",
        project_id="p1",
        script_id="s1",
        user_message="测试短片",
        style_mode=VideoStyleMode.DYNAMIC_IMAGE,
        generation_mode=GenerationMode.AUTO,
    )
    actions = session.available_actions()
    assert "delegate_script_design" in actions
    assert "tool_get_plan_summary" in actions
    assert "finish" in actions
    assert "delegate_video_gen" not in actions
    session.completed_step_types.add("script_design")
    actions_after = session.available_actions()
    assert "delegate_script_design" in actions_after
    assert "delegate_script_design" not in session.next_actions()


def test_react_session_next_actions_skips_completed():
    session = create_master_react_session(
        conversation_id="conv_next",
        project_id="p1",
        script_id="s1",
        user_message="测试",
        style_mode=VideoStyleMode.DYNAMIC_IMAGE,
        generation_mode=GenerationMode.AUTO,
    )
    assert "delegate_script_design" in session.next_actions()
    session.completed_step_types.add("script_design")
    next_acts = session.next_actions()
    assert "delegate_script_design" not in next_acts
    assert len(next_acts) >= 1


def test_build_master_react_system_contains_state_json():
    session = create_master_react_session(
        conversation_id="conv_json",
        project_id="p1",
        script_id="s1",
        user_message="JSON 测试",
        style_mode=VideoStyleMode.AI_VIDEO,
        generation_mode=GenerationMode.AUTO,
    )
    system = build_master_react_system(session)
    assert MASTER_STATE_HEADER in system
    state = json.loads(build_master_react_state_json(session))
    assert "delegate_script_design" in state["available_actions"]
    assert "tool_get_plan_summary" in state["available_actions"]
    assert "next_actions" in state
    assert state["task_brief"]

    messages = [{"role": "system", "content": system}]
    parsed = extract_master_state_json(messages)
    assert parsed is not None
    assert parsed["task_brief"] == state["task_brief"]


def test_build_master_react_state_excludes_completed_from_available():
    session = create_master_react_session(
        conversation_id="conv_dedup",
        project_id="p1",
        script_id="s1",
        user_message="去重测试",
        style_mode=VideoStyleMode.DYNAMIC_IMAGE,
        generation_mode=GenerationMode.AUTO,
    )
    session.completed_step_types.add("script_design")
    state = json.loads(build_master_react_state_json(session))
    assert "delegate_script_design" in state["completed_actions"]
    assert "delegate_script_design" not in state["available_actions"]
    assert "finish" in state["available_actions"]


def test_build_master_react_state_includes_execution_plan():
    session = create_master_react_session(
        conversation_id="conv_plan",
        project_id="p1",
        script_id="s1",
        user_message="Plan 测试",
        style_mode=VideoStyleMode.DYNAMIC_IMAGE,
        generation_mode=GenerationMode.AUTO,
    )
    session.execution_plan = {
        "version": 1,
        "goal": "测试",
        "steps": [],
        "runtime_summary": "进行中",
    }
    session.plan_status_history = ["步骤1完成"]
    session.last_remaining_plan = ["delegate_image_gen"]
    state = json.loads(build_master_react_state_json(session))
    assert state["execution_plan"]["goal"] == "测试"
    assert state["plan_status_history"] == ["步骤1完成"]
    assert state["last_remaining_plan"] == ["delegate_image_gen"]


@pytest.mark.asyncio
async def test_decide_master_session_requires_user_message(llm_config_with_key):
    session = create_master_react_session(
        conversation_id="conv_no_user",
        project_id="p1",
        script_id="s1",
        user_message="测试",
        style_mode=VideoStyleMode.DYNAMIC_IMAGE,
        generation_mode=GenerationMode.AUTO,
    )
    conversations = ConversationStore()
    with pytest.raises(RuntimeError, match="无用户消息"):
        await decide_master_session(
            LLMClient(llm_config_with_key),
            llm_config_with_key,
            session,
            conversations,
        )


@pytest.mark.asyncio
async def test_decide_master_session_with_user_in_store(llm_config_with_key):
    session = create_master_react_session(
        conversation_id="conv_with_user",
        project_id="p1",
        script_id="s1",
        user_message="做短片",
        style_mode=VideoStyleMode.DYNAMIC_IMAGE,
        generation_mode=GenerationMode.AUTO,
    )
    conversations = ConversationStore()
    conversations.add_user_message("conv_with_user", "p1", "s1", "做短片")
    decision = await decide_master_session(
        ScriptedLLMClient(),
        llm_config_with_key,
        session,
        conversations,
    )
    assert decision.action.startswith("delegate_")


@pytest.mark.asyncio
async def test_master_tool_get_plan_summary():
    store = MemoryStore()
    from core.models.entities import PlanDocument, Script, Project

    project = Project(title="P")
    store.add_project(project)
    script = Script(project_id=project.id, title="S")
    store.add_script(script)
    plan = PlanDocument(version=1, goal="测试", steps=[])
    store.set_plan(script.id, plan)

    executor = MasterToolExecutor(store)
    result = await executor.execute("tool_get_plan_summary", script.id)
    assert "计划版本" in result
