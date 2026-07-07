"""单元测试：ReActRunner 重复工具调用中止。"""

import pytest

from core.llm.agent.react_core import AgentRunContext, ReActDecision, ReActRunner
from core.llm.hook.react_guard import DuplicateActionAbortError
from core.conversation.store import ConversationStore
from core.events.emitter import EventEmitter


@pytest.mark.asyncio
async def test_react_runner_aborts_on_duplicate_action_signature():
    emitter = EventEmitter()
    conversations = ConversationStore()
    runner = ReActRunner(emitter, conversations)
    calls = {"n": 0}

    async def decide(_ctx: AgentRunContext) -> ReActDecision:
        calls["n"] += 1
        return ReActDecision(
            thought="查询资产",
            action="list_text_assets",
            action_input={"note": "same"},
        )

    async def act(_action: str, _ctx: AgentRunContext) -> str:
        return "ok"

    with pytest.raises(DuplicateActionAbortError, match="重复调用"):
        await runner.run_agent(
            agent_name="script_agent",
            display_name="剧本 Agent",
            task_brief="测试重复调用",
            work_context={
                "project_id": "proj_test",
                "script_id": "script_test",
                "conversation_id": "conv_dup",
            },
            script_id="script_test",
            step_id="step_dup",
            decide=decide,
            act=act,
        )

    assert calls["n"] == 2
