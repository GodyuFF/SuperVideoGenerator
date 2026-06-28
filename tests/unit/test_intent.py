"""超级视频大师 LLM 意图门卫测试。"""

import pytest

from core.a2ui.manager import ConfirmationManager
from core.agents.conversation import ConversationStore
from core.events.emitter import EventEmitter
from core.models.entities import GenerationMode, Project, Script, VideoStyleMode
from core.store.memory import MemoryStore
from core.super_video_master.intent import DEFAULT_DECLINE_REPLY, classify_user_intent
from core.super_video_master.super_video_master import SuperVideoMaster
from tests.conftest import inject_scripted_llm
from tests.support.scripted_llm import ScriptedLLMClient


@pytest.fixture
def intent_client():
    return ScriptedLLMClient()


@pytest.mark.asyncio
async def test_intent_allows_creative_message_without_video_keyword(intent_client):
    result = await classify_user_intent(
        intent_client, "用户私密创意内容", project_id="p1", script_id="s1"
    )
    assert result.in_scope is True


@pytest.mark.asyncio
async def test_intent_rejects_off_topic_message(intent_client):
    result = await classify_user_intent(
        intent_client, "今天天气怎么样", project_id="p1", script_id="s1"
    )
    assert result.in_scope is False
    assert result.reply


@pytest.mark.asyncio
async def test_intent_rejects_empty_message(intent_client):
    result = await classify_user_intent(intent_client, "   ", project_id="p1", script_id="s1")
    assert result.in_scope is False
    assert "请输入" in result.reply


@pytest.mark.asyncio
async def test_run_from_message_uses_llm_intent_not_keywords():
    """无「视频」关键词的创意描述也应进入流水线（由 LLM 门卫放行）。"""
    store = MemoryStore()
    emitter = EventEmitter()
    conversations = ConversationStore()
    confirmation = ConfirmationManager(emitter, default_timeout=5.0)
    master = SuperVideoMaster(store, emitter, confirmation, conversations)

    project = Project(title="测试项目")
    project.config.generation.mode = GenerationMode.AUTO
    project.config.style.mode = VideoStyleMode.DYNAMIC_IMAGE
    store.add_project(project)

    script = Script(project_id=project.id, title="第一集", duration_sec=60)
    store.add_script(script)

    inject_scripted_llm(master, VideoStyleMode.DYNAMIC_IMAGE)
    await master.run_from_message(project.id, script.id, "用户私密创意内容")

    master_msgs = conversations.list_messages(script.id, "master")
    assert not any(DEFAULT_DECLINE_REPLY in m.content for m in master_msgs)
