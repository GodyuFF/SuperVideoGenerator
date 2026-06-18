"""单元测试：ReAct 核心与子 Agent ReAct。"""

import pytest

from core.agents.conversation import ConversationStore
from core.agents.registry import AgentRegistry
from core.agents.react_core import MasterRunContext
from core.events.emitter import EventEmitter
from core.llm.client import LLMClient
from core.llm.react_decider import LLMReActDecider
from core.llm.rule_fallback import rule_decide_master
from core.llm.settings import LLMConfigManager
from core.logging.setup import setup_logging
from core.models.entities import GenerationMode, Project, Script, VideoStyleMode
from core.store.memory import MemoryStore
from core.super_video_master.actions import ACTION_TO_STEP


def _make_decider() -> LLMReActDecider:
    config = LLMConfigManager()
    config.update(use_llm_react=False)
    return LLMReActDecider(config, LLMClient(config))


@pytest.mark.asyncio
async def test_master_policy_dynamic_image_pipeline():
    """主 Agent 规则回退：动态图片模式跳过 video_gen。"""
    ctx = MasterRunContext(
        project_id="p1",
        script_id="s1",
        user_message="都市短片",
        style_mode=VideoStyleMode.DYNAMIC_IMAGE,
        generation_mode=GenerationMode.AUTO,
    )
    actions = []
    for _ in range(10):
        decision = rule_decide_master(ctx)
        if decision.action == "finish":
            break
        actions.append(decision.action)
        ctx.completed_step_types.add(ACTION_TO_STEP[decision.action])

    assert "delegate_video_gen" not in actions
    assert len(actions) == 5


@pytest.mark.asyncio
async def test_script_agent_react_isolated():
    """剧本 Agent 在隔离会话中 ReAct 执行。"""
    setup_logging("WARNING")
    store = MemoryStore()
    emitter = EventEmitter()
    conversations = ConversationStore()
    decider = _make_decider()
    registry = AgentRegistry(store, emitter, conversations, decider)
    agent = registry.get("script_agent")

    project = Project(title="测试")
    store.add_project(project)
    script = Script(project_id=project.id, title="S1")
    store.add_script(script)

    events = []

    async def capture(e):
        events.append(e)

    emitter.subscribe(capture)

    outputs = await agent.run(
        task_brief="生成都市题材剧本与文字资产。",
        work_context={"project_id": project.id, "script_id": script.id},
        script_id=script.id,
        step_id="step_test",
    )

    assert len(outputs) >= 3
    msgs = conversations.list_messages(script.id, "agent", "script_agent")
    assert any(m.role.value == "task" for m in msgs)
    assert any(m.role.value == "thought" for m in msgs)
    assert any(e.get("type") == "agent_react_finished" for e in events)
