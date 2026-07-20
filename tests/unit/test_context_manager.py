"""AgentContextManager 动态槽位测试。"""

from core.llm.agent.react_core import AgentRunContext
from core.llm.prompt.context_manager import AgentContextManager
from core.models.entities import Project, Script
from core.store.memory import MemoryStore


def test_sub_agent_react_inputs():
    store = MemoryStore()
    project = Project(title="我的项目")
    store.add_project(project)
    ctx = AgentRunContext(
        task_brief="写剧本",
        work_context={
            "style_mode": "storybook",
            "project_id": project.id,
            "script_id": "s1",
            "conversation_id": "conv1",
        },
        script_id="s1",
        step_id="step1",
        agent_name="script_agent",
        observations=["obs1"],
        history_summary="较早摘要",
        iteration=2,
    )
    inputs = AgentContextManager.sub_agent.build_react_inputs(
        ctx,
        role_prompt="你是剧本 Agent",
        display_name="剧本 Agent",
        available_actions=["parse_brief", "finish"],
        store=store,
    )
    assert inputs["task_brief"] == "写剧本"
    assert "parse_brief" in inputs["available_actions"]
    assert inputs["extra"]["history_summary"] == "较早摘要"
    assert inputs["extra"]["project_context"]["project_id"] == project.id
    assert inputs["extra"]["project_context"]["project_title"] == "我的项目"
    assert inputs["extra"]["project_context"]["script_id"] == "s1"
    assert "role_description" not in inputs


def test_sub_agent_action_slots():
    store = MemoryStore()
    project = Project(title="P1")
    store.add_project(project)
    script = Script(project_id=project.id, title="S1")
    store.add_script(script)
    ctx = AgentRunContext(
        task_brief="生图",
        work_context={"script_id": script.id, "project_id": project.id},
        script_id=script.id,
        step_id="step1",
        agent_name="image_agent",
        completed_actions={"scan_text_assets"},
        observations=["已扫描"],
    )
    slots = AgentContextManager.sub_agent.build_action_slots(
        ctx,
        store,
        role_prompt="你是图片 Agent",
        display_name="图片 Agent",
        action="generate_images",
        store_context_block="",
    )
    assert slots["current_action"] == "generate_images"
    assert "scan_text_assets" in slots["completed_actions"]
    assert "已扫描" in slots["observations_block"]
    assert project.id in slots["work_context_line"]
    assert "S1" in slots["work_context_line"]
