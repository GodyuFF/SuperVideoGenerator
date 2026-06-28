"""单元测试：ReAct 核心与子 Agent ReAct。"""

import pytest

from core.conversation import ConversationStore
from core.agents.react_core import AgentRunContext
from core.agents.registry import AgentRegistry
from core.events.emitter import EventEmitter
from core.llm.client import LLMClient
from core.llm.react_decide import decide_sub_agent, require_llm
from core.llm.settings import LLMConfigManager
from core.logging.setup import setup_logging
from core.models.entities import Project, Script
from core.store.memory import MemoryStore
from tests.support.scripted_llm import ScriptedLLMClient


@pytest.mark.asyncio
async def test_script_agent_react_isolated(llm_config_with_key):
    """剧本 Agent 在隔离会话中通过 LLM ReAct 执行。"""
    setup_logging("WARNING")
    store = MemoryStore()
    emitter = EventEmitter()
    conversations = ConversationStore()
    scripted = ScriptedLLMClient()
    registry = AgentRegistry(
        store, emitter, conversations, llm_config_with_key, scripted
    )
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


@pytest.mark.asyncio
async def test_decider_requires_llm():
    """未配置 API Key 时应拒绝决策。"""
    config = LLMConfigManager()
    config.update(use_llm_react=False)
    with pytest.raises(RuntimeError, match="LLM"):
        require_llm(config)

    ctx = AgentRunContext(
        task_brief="t",
        work_context={},
        script_id="s1",
        step_id="step1",
        agent_name="script_agent",
    )
    with pytest.raises(RuntimeError, match="LLM"):
        await decide_sub_agent(
            LLMClient(config),
            config,
            ctx,
            display_name="剧本 Agent",
            role_prompt="角色",
            action_pipeline=["parse_brief"],
        )
