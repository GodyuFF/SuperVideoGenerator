"""单元测试：ReActSession 与主编排工具。"""

import pytest

from core.llm.react_session import (
    create_master_react_session,
    new_conversation_id,
)
from core.llm.xml_protocol import build_react_session_xml
from core.models.entities import GenerationMode, VideoStyleMode
from core.tools.master_tools import MasterToolExecutor
from core.store.memory import MemoryStore


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


def test_build_react_session_xml_contains_session_fields():
    session = create_master_react_session(
        conversation_id="conv_xml",
        project_id="p1",
        script_id="s1",
        user_message="XML 测试",
        style_mode=VideoStyleMode.AI_VIDEO,
        generation_mode=GenerationMode.AUTO,
    )
    xml = build_react_session_xml(session)
    assert "<conversation_id>conv_xml</conversation_id>" in xml
    assert "<agent_name>super_video_master</agent_name>" in xml
    assert "<action>tool_get_plan_summary</action>" in xml
    assert "<delegate_action>delegate_script_design</delegate_action>" in xml


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
