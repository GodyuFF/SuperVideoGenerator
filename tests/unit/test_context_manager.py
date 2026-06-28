"""AgentContextManager 动态槽位测试。"""

from core.agents.react_core import AgentRunContext
from core.prompt.context_manager import AgentContextManager
from core.store.memory import MemoryStore


def test_sub_agent_react_inputs():
    ctx = AgentRunContext(
        task_brief="写剧本",
        work_context={"style_mode": "dynamic_image", "project_id": "p1"},
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
    )
    assert inputs["task_brief"] == "写剧本"
    assert "parse_brief" in inputs["available_actions"]
    assert inputs["extra"]["history_summary"] == "较早摘要"
    assert "role_description" not in inputs


def test_sub_agent_action_slots():
    store = MemoryStore()
    ctx = AgentRunContext(
        task_brief="生图",
        work_context={"script_id": "s1", "project_id": "p1"},
        script_id="s1",
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
