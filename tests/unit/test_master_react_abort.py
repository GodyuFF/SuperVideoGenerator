"""主编排 ReAct 错误中断行为测试。"""

import pytest

from core.llm.a2ui.manager import ConfirmationManager
from core.conversation import ConversationIndex, ConversationStore
from core.events.emitter import EventEmitter
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
