"""Chat 多轮消息映射与历史构建测试。"""

import json

from core.conversation.store import (
    ConversationMessage,
    ConversationStore,
    MessageKind,
    MessageRole,
)
from core.llm.model.chat_message import (
    anthropic_to_canonical_messages,
    canonical_to_anthropic_messages,
    flatten_content_blocks,
    format_action_content,
    message_content_text,
    normalize_content,
    parse_action_content,
    text_block,
    thinking_block,
    tool_message,
    tool_result_block,
    tool_use_block,
)
from core.llm.prompt.chat_messages import (
    MASTER_STATE_HEADER,
    MASTER_STATE_INSTRUCTIONS,
    REACT_STATE_HEADER,
    build_agent_react_chat_history,
    build_llm_messages,
    build_llm_request,
    build_llm_request_ordered,
    build_master_react_chat_history,
    conversation_message_to_chat,
    conversation_messages_to_chat_blocks,
    extract_master_state_json,
    fit_chat_history,
    last_user_content,
    messages_to_chat_history,
    master_channel_has_user,
)


def _msg(
    role: MessageRole,
    content: str | list,
    agent: str = "",
    *,
    message_kind: MessageKind = MessageKind.DEFAULT,
    tool_call_id: str = "",
) -> ConversationMessage:
    return ConversationMessage(
        conversation_id="conv1",
        project_id="p1",
        script_id="s1",
        channel="agent" if agent else "master",
        agent_name=agent,
        role=role,
        content=content,
        message_kind=message_kind,
        tool_call_id=tool_call_id,
    )


def _react_turn(
    thought: str,
    action: str,
    action_input: dict,
    observation: str,
    agent: str = "script_agent",
) -> list[ConversationMessage]:
    tool_id = "call_msg_test"
    return [
        _msg(
            MessageRole.ASSISTANT,
            [
                text_block(thought),
                tool_use_block(tool_id=tool_id, name=action, input_data=action_input),
            ],
            agent,
        ),
        _msg(
            MessageRole.TOOL,
            observation,
            agent,
            tool_call_id=tool_id,
        ),
    ]


def test_parse_action_content_json_roundtrip():
    action_input = {"observation": "补充", "questions": [{"id": "theme", "prompt": "主题"}]}
    content = format_action_content("ask_user_question", action_input)
    action, parsed = parse_action_content(content)
    assert action == "ask_user_question"
    assert parsed == action_input
    assert "raw" not in parsed


def test_parse_action_content_python_repr_fallback():
    action, parsed = parse_action_content(
        "ask_user_question: {'observation': '补充', 'questions': []}"
    )
    assert action == "ask_user_question"
    assert parsed.get("observation") == "补充"
    assert "raw" not in parsed


def test_conversation_message_role_mapping():
    user_chat = conversation_message_to_chat(_msg(MessageRole.USER, "你好"))
    assert user_chat == {
        "role": "user",
        "content": [{"type": "text", "text": "你好"}],
    }
    summary_chat = conversation_message_to_chat(
        _msg(MessageRole.ASSISTANT, "收到", message_kind=MessageKind.SUMMARY)
    )
    assert summary_chat == {
        "role": "assistant",
        "content": [{"type": "text", "text": "收到"}],
    }
    tool_chat = conversation_message_to_chat(
        _msg(MessageRole.TOOL, "完成", "script_agent", tool_call_id="call_1")
    )
    assert tool_chat["role"] == "tool"
    assert tool_chat["tool_call_id"] == "call_1"
    task_blocks = conversation_messages_to_chat_blocks(
        [
            _msg(
                MessageRole.ASSISTANT,
                "任务简报：写剧本",
                "script_agent",
                message_kind=MessageKind.TASK_BRIEF,
            )
        ],
        include_task=False,
    )
    assert task_blocks == []
    task_blocks = conversation_messages_to_chat_blocks(
        [
            _msg(
                MessageRole.ASSISTANT,
                "任务简报：写剧本",
                "script_agent",
                message_kind=MessageKind.TASK_BRIEF,
            )
        ],
        include_task=True,
    )
    assert task_blocks[0]["role"] == "assistant"
    assert task_blocks[0]["content"][0]["text"].startswith("任务简报")


def test_react_turn_maps_to_assistant_and_tool():
    msgs = _react_turn("先分析", "parse_brief", {"x": 1}, "解析完成")
    blocks = conversation_messages_to_chat_blocks(msgs)
    assert len(blocks) == 2
    assert blocks[0]["role"] == "assistant"
    assert blocks[0]["content"][0]["type"] == "text"
    assert blocks[0]["content"][1]["type"] == "tool_use"
    assert blocks[0]["content"][1]["name"] == "parse_brief"
    assert blocks[1]["role"] == "tool"
    assert blocks[1]["tool_call_id"] == "call_msg_test"
    assert blocks[1]["content"][0]["text"] == "解析完成"


def test_thinking_block_preserved_in_wire_roundtrip():
    canonical = [
        {
            "role": "assistant",
            "content": [
                thinking_block("推理链", signature="sig_1"),
                tool_use_block(tool_id="call_1", name="finish", input_data={}),
            ],
        },
        tool_message("call_1", "完成"),
    ]
    wire = canonical_to_anthropic_messages(canonical)
    assert wire[0]["content"][0] == {
        "type": "thinking",
        "thinking": "推理链",
        "signature": "sig_1",
    }
    roundtrip = anthropic_to_canonical_messages(wire)
    assert roundtrip[0]["content"][0]["type"] == "thinking"
    assert roundtrip[0]["content"][0]["thinking"] == "推理链"
    assert roundtrip[0]["content"][0]["signature"] == "sig_1"


def test_legacy_text_before_tool_use_converted_to_thinking_on_wire():
    canonical = [
        {
            "role": "assistant",
            "content": [
                text_block("旧版思考"),
                tool_use_block(tool_id="call_1", name="finish", input_data={}),
            ],
        },
    ]
    wire = canonical_to_anthropic_messages(canonical)
    assert wire[0]["content"][0]["type"] == "thinking"
    assert wire[0]["content"][0]["thinking"] == "旧版思考"


def test_canonical_to_anthropic_wire_format():
    canonical = [
        {"role": "assistant", "content": [
            text_block("思考"),
            tool_use_block(tool_id="call_1", name="finish", input_data={}),
        ]},
        tool_message("call_1", "完成"),
    ]
    wire = canonical_to_anthropic_messages(canonical)
    assert wire[0]["role"] == "assistant"
    assert wire[0]["content"][0]["type"] == "thinking"
    assert wire[0]["content"][0]["thinking"] == "思考"
    assert wire[0]["content"][1]["type"] == "tool_use"
    assert wire[1]["role"] == "user"
    assert wire[1]["content"][0]["tool_use_id"] == "call_1"


def test_orphan_tool_result_becomes_user_tool_result_in_wire():
    canonical = [
        {"role": "assistant", "content": [text_block("先写剧本")]},
        {"role": "assistant", "content": [
            tool_result_block(tool_use_id="call_unknown", content="失败"),
        ]},
    ]
    wire = canonical_to_anthropic_messages(canonical)
    assert len(wire) == 2
    assert wire[0]["role"] == "assistant"
    assert wire[1]["role"] == "user"
    assert wire[1]["content"][0]["type"] == "tool_result"


def test_anthropic_to_canonical_roundtrip():
    wire = [
        {"role": "assistant", "content": [
            {"type": "text", "text": "想"},
            {"type": "tool_use", "id": "c1", "name": "finish", "input": {}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "c1", "content": "ok"},
        ]},
    ]
    canonical = anthropic_to_canonical_messages(wire)
    assert len(canonical) == 2
    assert canonical[0]["role"] == "assistant"
    assert canonical[1]["role"] == "tool"
    assert canonical[1]["tool_call_id"] == "c1"


def test_fit_chat_history_keeps_recent_messages():
    messages = [
        {"role": "user", "content": [text_block(f"消息{i}")]} for i in range(20)
    ]
    kept, summary = fit_chat_history(messages, window_size=5, max_chars=500)
    assert len(kept) <= 5
    assert kept[-1]["content"][0]["text"] == "消息19"
    assert "已压缩" in summary


def test_build_master_react_chat_history_from_store():
    store = ConversationStore()
    store.add_user_message("conv1", "p1", "s1", "做短片")
    store.add_orphan_observation("conv1", "p1", "s1", "工具返回计划", channel="master")

    history = build_master_react_chat_history(store, "conv1")
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"][0]["type"] == "text"
    assert history[1]["content"][0]["text"].startswith("[观察]")


def test_build_agent_react_chat_history_from_store():
    store = ConversationStore()
    store.add_task_brief("conv1", "p1", "s1", "写剧本", "script_agent")
    store.add(
        "conv1",
        "p1",
        "s1",
        "agent",
        MessageRole.ASSISTANT,
        "解析",
        "script_agent",
    )

    history = build_agent_react_chat_history(store, "conv1", "script_agent")
    assert len(history) == 1
    assert history[0]["content"][0]["type"] == "text"
    assert history[0]["role"] == "assistant"


def test_master_channel_has_user():
    store = ConversationStore()
    assert not master_channel_has_user(store, "conv1")
    store.add_user_message("conv1", "p1", "s1", "hi")
    assert master_channel_has_user(store, "conv1")


def test_build_llm_messages_history_only_without_turn_user():
    history = [
        {"role": "user", "content": [text_block("你好")]},
        {"role": "assistant", "content": [text_block("收到")]},
    ]
    messages = build_llm_messages(
        system_prompt="你是主编排",
        history=history,
    )
    assert messages[0]["role"] == "system"
    assert len(messages) == 3
    assert messages[-1]["content"] == [text_block("收到")]


def test_extract_master_state_json_from_system():
    state = {"available_actions": ["finish"], "completed_actions": ["无"]}
    system = f"协议\n\n{MASTER_STATE_HEADER}\n{json.dumps(state, ensure_ascii=False)}"
    parsed = extract_master_state_json(
        [{"role": "system", "content": [text_block(system)]}]
    )
    assert parsed == state


def test_extract_master_state_json_with_hint_before_instructions():
    state = {
        "available_actions": ["delegate_script_design", "finish"],
        "completed_actions": ["无"],
        "next_actions": ["delegate_script_design"],
    }
    hint = "已完成：无；建议下一步：delegate_script_design。action 必须且只能从 available_actions 中选择。"
    system = (
        f"协议\n\n{MASTER_STATE_HEADER}\n"
        f"{json.dumps(state, ensure_ascii=False)}\n\n{hint}\n\n{MASTER_STATE_INSTRUCTIONS}"
    )
    parsed = extract_master_state_json(
        [{"role": "system", "content": [text_block(system)]}]
    )
    assert parsed == state


def test_build_llm_messages_assembles_system_history_turn():
    history = [
        {"role": "user", "content": [text_block("你好")]},
        {"role": "assistant", "content": [text_block("收到")]},
    ]
    messages = build_llm_messages(
        system_prompt="你是助手",
        history=history,
        turn_user='{"available_actions": ["finish"]}',
    )
    assert messages[0] == {
        "role": "system",
        "content": [text_block("你是助手")],
    }
    assert len(messages) == 4
    assert messages[-1]["role"] == "user"
    assert last_user_content(messages) == '{"available_actions": ["finish"]}'


def test_messages_to_chat_history_skips_unknown():
    msgs = [_msg(MessageRole.USER, "a")]
    assert messages_to_chat_history(msgs) == [
        {"role": "user", "content": [text_block("a")]}
    ]


def test_flatten_content_blocks():
    blocks = [
        thinking_block("想"),
        tool_use_block(tool_id="call_1", name="act", input_data={"k": "v"}),
        tool_result_block(tool_use_id="call_1", content="结果"),
    ]
    flat = flatten_content_blocks(blocks)
    assert "想" in flat
    assert "[行动]" in flat
    assert "[观察]" in flat


def test_normalize_content_accepts_string():
    assert normalize_content("hello") == [text_block("hello")]


def test_build_llm_request_no_system_in_messages():
    req = build_llm_request(
        system_prompt="sys",
        history=[{"role": "user", "content": [text_block("u")]}],
    )
    assert req.system == "sys"
    assert all(m.get("role") != "system" for m in req.messages)


def test_build_llm_request_ordered_anchor_history_turn():
    history = [
        {"role": "assistant", "content": [text_block("思考")]},
        {"role": "tool", "content": [text_block("结果")], "tool_call_id": "call_1"},
    ]
    req = build_llm_request_ordered(
        system_prompt="sys",
        anchor_user="任务简报：写剧本",
        history=history,
        turn_user='{"available_actions": ["finish"]}',
    )
    assert req.messages[0]["role"] == "user"
    assert message_content_text(req.messages[0]["content"]) == "任务简报：写剧本"
    assert req.messages[1]["role"] == "assistant"
    assert req.messages[-1]["role"] == "user"
    assert "available_actions" in message_content_text(req.messages[-1]["content"])


def test_fit_chat_history_pins_first_user():
    messages = [{"role": "user", "content": [text_block("原始诉求")]}]
    messages.extend(
        {"role": "user", "content": [text_block(f"消息{i}")]} for i in range(30)
    )
    kept, _ = fit_chat_history(messages, window_size=5, max_chars=200, pin_first_user=True)
    assert kept[0]["role"] == "user"
    assert kept[0]["content"][0]["text"] == "原始诉求"


def test_extract_master_state_json_from_llm_request():
    state = {"available_actions": ["finish"]}
    req = build_llm_request(
        system_prompt=f"{MASTER_STATE_HEADER}\n{json.dumps(state)}",
        history=[{"role": "user", "content": [text_block("hi")]}],
    )
    assert extract_master_state_json(req) == state


def test_extract_master_state_json_from_turn_user():
    state = {"available_actions": ["delegate_script_design", "finish"], "completed_actions": ["无"]}
    turn = f"{MASTER_STATE_HEADER}\n{json.dumps(state, ensure_ascii=False)}"
    req = build_llm_request(
        system_prompt="静态协议与角色",
        history=[{"role": "user", "content": [text_block("用户诉求")]}],
        turn_user=turn,
    )
    assert extract_master_state_json(req) == state
    assert REACT_STATE_HEADER not in req.system
