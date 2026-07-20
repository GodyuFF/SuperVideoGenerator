"""主编排 ReAct 错误中断行为测试。"""

import json

import pytest

from core.llm.a2ui.manager import ConfirmationManager
from core.conversation import ConversationIndex, ConversationStore
from core.events.emitter import EventEmitter
from core.llm.client.tool_calls import ToolCallResult
from core.logging.setup import setup_logging
from core.models.entities import GenerationMode, Project, Script, ScriptStatus, VideoStyleMode
from core.store.memory import MemoryStore
from core.super_video_master.super_video_master import SuperVideoMaster
from tests.conftest import setup_auto_confirm
from tests.support.scripted_llm import ScriptedLLMClient


class FailingDecideLLM(ScriptedLLMClient):
    """主编排决策始终失败，用于验证中断逻辑。"""

    async def complete_tool_calls(self, request, **kwargs):
        raise RuntimeError("LLM 未返回 tool_calls")


class ExclusiveMixThenFinishLLM(ScriptedLLMClient):
    """首轮混用 delegate_agent+tool_*，次轮 finish，验证独占错误可恢复。"""

    def __init__(self) -> None:
        super().__init__()
        self.master_decide_count = 0

    async def complete_tool_calls(self, request, **kwargs):
        self._record_scripted_tokens()
        ctx = kwargs.get("log_context") or {}
        if str(ctx.get("role", "")) == "master":
            self.master_decide_count += 1
            if self.master_decide_count == 1:
                return ToolCallResult(
                    content="错误地同轮混用",
                    tool_calls=[
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "delegate_agent",
                                "arguments": json.dumps(
                                    {
                                        "agent_id": "script_agent",
                                        "plan_status": "委派剧本",
                                        "remaining_plan": [],
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        },
                        {
                            "id": "c2",
                            "type": "function",
                            "function": {
                                "name": "tool_list_assets",
                                "arguments": "{}",
                            },
                        },
                    ],
                )
            return ToolCallResult(
                content="纠正后结束",
                tool_calls=[
                    {
                        "id": "c3",
                        "type": "function",
                        "function": {
                            "name": "finish",
                            "arguments": json.dumps(
                                {
                                    "plan_status": "目标已结束",
                                    "remaining_plan": [],
                                },
                                ensure_ascii=False,
                            ),
                        },
                    },
                ],
            )
        return await super().complete_tool_calls(request, **kwargs)


@pytest.fixture
def abort_harness():
    setup_logging("WARNING")
    store = MemoryStore()
    emitter = EventEmitter()
    conversations = ConversationStore()
    conversation_index = ConversationIndex()
    confirmation = ConfirmationManager(emitter, default_timeout=5.0)
    master = SuperVideoMaster(
        store, emitter, confirmation, conversations, conversation_index=conversation_index
    )
    project = Project(title="P")
    project.config.generation.mode = GenerationMode.AUTO
    store.add_project(project)
    script = Script(project_id=project.id, title="S", duration_sec=60)
    store.add_script(script)
    master._llm_config.update(api_key="test-key", use_llm_react=True)
    master._llm_client = master._react._llm_client = FailingDecideLLM()
    setup_auto_confirm(emitter, confirmation)
    return store, emitter, master, project, script


@pytest.mark.asyncio
async def test_run_from_message_aborts_on_decide_failure(abort_harness):
    """LLM 决策失败时应立即中断，剧本标记 failed，且不调用摘要 LLM。"""
    store, emitter, master, project, script = abort_harness
    events: list[dict] = []

    async def capture(e: dict) -> None:
        events.append(e)

    emitter.subscribe(capture)

    summary_calls = 0
    original_complete = master._llm_client.complete

    async def track_complete(*args, **kwargs):
        nonlocal summary_calls
        summary_calls += 1
        return await original_complete(*args, **kwargs)

    master._llm_client.complete = track_complete  # type: ignore[method-assign]

    conv_id, summary = await master.run_from_message(
        project.id, script.id, "做短片", conversation_id=None
    )

    assert script.status == ScriptStatus.FAILED
    assert "执行失败" in summary
    assert summary_calls == 0
    assert any(e.get("type") == "execution_failed" for e in events)


@pytest.mark.asyncio
async def test_exclusive_tool_batch_error_returned_and_recoverable(abort_harness):
    """delegate_agent 同轮混用时把报错写回 observation，并允许下一轮纠正。"""
    store, emitter, master, project, script = abort_harness
    llm = ExclusiveMixThenFinishLLM()
    master._llm_client = master._react._llm_client = llm
    events: list[dict] = []

    async def capture(e: dict) -> None:
        events.append(e)

    emitter.subscribe(capture)

    conv_id, summary = await master.run_from_message(
        project.id, script.id, "做短片", conversation_id=None
    )

    assert llm.master_decide_count >= 2
    obs_events = [
        e
        for e in events
        if e.get("type") == "react_observation"
        and "不可与其他 tool 同轮调用" in str(e.get("observation", ""))
    ]
    assert obs_events, "应将独占混用报错作为 observation 返回"
    assert not any(
        e.get("type") == "execution_failed"
        and "不可与其他 tool 同轮调用" in str(e.get("error", ""))
        for e in events
    )
    master_msgs = master._conversations.list_messages(conv_id, channel="master")
    assert any(
        "不可与其他 tool 同轮调用" in (
            m.content if isinstance(m.content, str) else str(m.content)
        )
        for m in master_msgs
    )