"""ask_user_question 工具与 A2UI 集成测试。"""

import asyncio

import pytest

from core.llm.a2ui.manager import ConfirmationManager
from core.llm.a2ui.schemas import A2UIConfirmationResponse
from core.llm.tools.shared.ask_user import (
    execute_ask_user_question,
    format_ask_user_observation,
    merge_user_answers_into_brief,
)
from core.llm.tools.shared.agent_tools import ASK_USER_QUESTION_ACTION, pipeline_actions
from core.events.emitter import EventEmitter
from core.llm.master import create_master_react_session
from core.models.entities import GenerationMode, VideoStyleMode
from core.llm.prompt.tools.registry import build_master_react_tools, build_sub_agent_react_tools
from core.llm.prompt.tools.schemas import action_input_schema


def test_master_react_tools_always_include_ask_user_question():
    tools = build_master_react_tools(["finish"])
    names = [t.name for t in tools]
    assert ASK_USER_QUESTION_ACTION in names
    ask = next(t for t in tools if t.name == ASK_USER_QUESTION_ACTION)
    assert "observation" in ask.input_schema["required"]
    assert "questions" in ask.input_schema["required"]
    assert "plan_status" in ask.input_schema["required"]
    assert "remaining_plan" in ask.input_schema["required"]


def test_sub_agent_react_tools_always_include_ask_user_question():
    tools = build_sub_agent_react_tools("script_agent", ["parse_brief", "finish"])
    names = [t.name for t in tools]
    assert ASK_USER_QUESTION_ACTION in names


def test_master_session_available_actions_include_ask_user_question():
    session = create_master_react_session(
        conversation_id="conv_ask",
        project_id="p1",
        script_id="s1",
        user_message="测试",
        style_mode=VideoStyleMode.STORYBOOK,
        generation_mode=GenerationMode.AUTO,
    )
    actions = session.available_actions()
    assert ASK_USER_QUESTION_ACTION in actions


def test_format_ask_user_observation_includes_values_json():
    obs = format_ask_user_observation("需要补充主题", {"theme": "科幻", "duration_sec": 60})
    assert "需要补充主题" in obs
    assert "用户回答：" in obs
    assert '"theme": "科幻"' in obs
    assert '"duration_sec": 60' in obs


def test_format_ask_user_observation_empty_values():
    assert format_ask_user_observation("仅观察", {}) == "仅观察"


def test_merge_user_answers_into_brief():
    brief = "用户创意：都市题材"
    merged = merge_user_answers_into_brief(
        brief,
        {"theme": "科幻", "duration_sec": 90, "confirm_checkbox": True},
    )
    assert "用户补充：" in merged
    assert "theme: 科幻" in merged
    assert "duration_sec: 90" in merged
    assert "confirm_checkbox" not in merged


def test_ask_user_question_action_schema():
    schema = action_input_schema(ASK_USER_QUESTION_ACTION)
    props = schema["properties"]
    assert "questions" in props
    assert "observation" in props
    assert "title" in props


def test_questions_to_components_select_defaults_to_first_option():
    from core.llm.tools.shared.ask_user import _questions_to_components

    components = _questions_to_components(
        [
            {
                "id": "style_mode",
                "prompt": "视频风格",
                "component": "select",
                "required": True,
                "options": [
                    {"label": "故事书", "value": "storybook"},
                    {"label": "AI 视频", "value": "ai_video"},
                ],
            }
        ]
    )
    assert len(components) == 1
    assert components[0].value == "storybook"


def test_questions_to_components_select_keeps_explicit_default():
    from core.llm.tools.shared.ask_user import _questions_to_components

    components = _questions_to_components(
        [
            {
                "id": "style_mode",
                "prompt": "视频风格",
                "component": "select",
                "default": "ai_video",
                "options": [
                    {"label": "故事书", "value": "storybook"},
                    {"label": "AI 视频", "value": "ai_video"},
                ],
            }
        ]
    )
    assert components[0].value == "ai_video"


@pytest.mark.asyncio
async def test_execute_ask_user_question_collects_values():
    emitter = EventEmitter()
    events: list[dict] = []

    async def capture(e: dict) -> None:
        events.append(e)

    emitter.subscribe(capture)
    mgr = ConfirmationManager(emitter, default_timeout=5.0)

    async def answer() -> None:
        await asyncio.sleep(0.05)
        event = events[0]
        mgr.resolve(
            A2UIConfirmationResponse(
                confirmation_id=str(event["confirmation_id"]),
                approved=True,
                values={"theme": "科幻", "duration_sec": "60"},
            )
        )

    task = asyncio.create_task(answer())
    observation, values = await execute_ask_user_question(
        mgr,
        {
            "observation": "需要补充主题",
            "title": "补充剧本信息",
            "questions": [
                {"id": "theme", "prompt": "主题", "component": "text"},
                {"id": "duration_sec", "prompt": "时长", "component": "text"},
            ],
        },
        step_id="script_1",
    )
    await task
    assert values == {"theme": "科幻", "duration_sec": "60"}
    assert "需要补充主题" in observation or "已收集" in observation
    assert events[0]["kind"] == "generic"


@pytest.mark.asyncio
async def test_execute_ask_user_question_rejected():
    emitter = EventEmitter()
    mgr = ConfirmationManager(emitter, default_timeout=5.0)

    async def reject() -> None:
        await asyncio.sleep(0.02)
        conf_id = next(iter(mgr._pending))
        mgr.resolve(
            A2UIConfirmationResponse(confirmation_id=conf_id, approved=False)
        )

    task = asyncio.create_task(reject())
    observation, values = await execute_ask_user_question(
        mgr,
        {
            "observation": "询问",
            "questions": [{"id": "q1", "prompt": "问题", "component": "text"}],
        },
    )
    await task
    assert values == {}
    assert "取消" in observation


def test_pipeline_actions_have_action_input_schema():
    """各 Agent 流水线 action 均应有非空 action input_schema。"""
    for agent_name in (
        "script_agent",
        "image_agent",
        "storyboard_agent",
        "video_agent",
        "tts_agent",
        "editing_agent",
    ):
        for action in pipeline_actions(agent_name):
            schema = action_input_schema(action)
            props = schema.get("properties") or {}
            assert props, f"{agent_name}.{action} 缺少 properties"
            assert "observation" in props, f"{agent_name}.{action} 缺少 observation"
