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
    _with_summary_prefix,
    apply_snippet_chat_history,
    build_agent_react_chat_history,
    build_llm_request,
    build_llm_request_ordered,
    build_master_react_chat_history,
    conversation_message_to_chat,
    conversation_messages_to_chat_blocks,
    extract_react_state_json,
    fit_chat_history,
    last_user_content,
    messages_to_chat_history,
    master_channel_has_user,
    repair_tool_message_pairs,
    split_messages_for_compression,
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


def test_canonical_to_anthropic_wire_format():
    canonical = [
        {"role": "assistant", "content": [
            thinking_block("思考"),
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


def assert_wire_tool_pairs_valid(wire: list[dict]) -> None:
    """断言 wire 中每个 tool_result 均有上一条 assistant 的匹配 tool_use。"""
    for index, msg in enumerate(wire):
        if msg.get("role") != "user":
            continue
        for block in msg.get("content", []):
            if block.get("type") != "tool_result":
                continue
            assert index > 0 and wire[index - 1].get("role") == "assistant"
            tool_use_ids = {
                b.get("id")
                for b in wire[index - 1].get("content", [])
                if b.get("type") == "tool_use"
            }
            assert block.get("tool_use_id") in tool_use_ids


def test_orphan_tool_result_becomes_observation_text_in_wire():
    canonical = [
        {"role": "assistant", "content": [text_block("先写剧本")]},
        {"role": "assistant", "content": [
            tool_result_block(tool_use_id="call_unknown", content="失败"),
        ]},
    ]
    wire = canonical_to_anthropic_messages(canonical)
    assert len(wire) == 2
    assert wire[0]["role"] == "assistant"
    assert wire[1]["role"] == "assistant"
    assert wire[1]["content"][0]["type"] == "text"
    assert "[观察]" in wire[1]["content"][0]["text"]
    assert_wire_tool_pairs_valid(wire)


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


def test_fit_chat_history_snippet_contains_action_not_char_count():
    """压缩摘要应含行动名/观察语义，而非 wire JSON 字符数。"""
    long_obs = "已完成 script_design，剧本已落盘。" + ("x" * 800)
    messages: list[dict] = [
        {"role": "user", "content": [text_block("做都市情感短片")]},
        {
            "role": "assistant",
            "content": [
                thinking_block("先委派剧本"),
                tool_use_block(
                    tool_id="call_1",
                    name="delegate_agent",
                    input_data={
                        "observation": "开始写剧本",
                        "plan_status": "进行中",
                        "remaining_plan": ["分镜"],
                    },
                ),
            ],
        },
        tool_message("call_1", long_obs),
    ]
    # 追加多条消息以触发滑窗压缩
    for i in range(12):
        messages.append(
            {"role": "assistant", "content": [text_block(f"轮次{i} " + ("y" * 400))]}
        )

    _, summary = fit_chat_history(messages, window_size=4, max_chars=1200, pin_first_user=True)
    assert "已压缩" in summary
    assert "delegate_agent" in summary or "已完成" in summary or "剧本" in summary
    assert "[assistant] 1198" not in summary
    assert not any(line.strip().endswith("] 137") for line in summary.splitlines())


def test_fit_chat_history_preserves_tool_turn():
    """滑窗压缩不得拆开 assistant(tool_use)+tool 轮次。"""
    messages: list[dict] = [
        {"role": "user", "content": [text_block("做短片")]},
        {
            "role": "assistant",
            "content": [
                tool_use_block(tool_id="call_1", name="delegate_agent", input_data={"agent_id": "script_agent"}),
            ],
        },
        tool_message("call_1", "剧本已落盘"),
    ]
    for i in range(15):
        messages.append({"role": "assistant", "content": [text_block(f"轮次{i} " + ("z" * 300))]})

    kept, _ = fit_chat_history(messages, window_size=4, max_chars=800, pin_first_user=True)
    compressed = apply_snippet_chat_history(messages, pin_first_user=True)
    wire = canonical_to_anthropic_messages(compressed)
    assert_wire_tool_pairs_valid(wire)
    tool_roles = [m.get("role") for m in compressed]
    if "tool" in tool_roles:
        tool_index = tool_roles.index("tool")
        assert compressed[tool_index - 1]["role"] == "assistant"
        assert any(
            b.get("type") == "tool_use"
            for b in normalize_content(compressed[tool_index - 1].get("content"))
        )


def test_summary_prefix_with_leading_tool_message():
    """摘要前缀合并 user 后，孤立 tool 应修复为可发送 wire。"""
    history = [
        tool_message("call_msg_2a6cec9ef45e", "工具返回结果"),
        {"role": "assistant", "content": [text_block("后续回复")]},
    ]
    result = repair_tool_message_pairs(
        _with_summary_prefix(history, "（已压缩较早对话）\n- 用户诉求摘要")
    )
    wire = canonical_to_anthropic_messages(result)
    assert_wire_tool_pairs_valid(wire)
    assert result[0]["role"] == "user"
    assert "已压缩较早对话" in message_content_text(result[0]["content"])
    assert result[1]["role"] == "assistant"
    assert "[观察]" in message_content_text(result[1]["content"])


def test_repair_partial_tool_use_turn():
    """assistant 含多个 tool_use 但仅部分有 tool 结果时，未配对 tool_use 应展平。"""
    assistant = {
        "role": "assistant",
        "content": [
            tool_use_block(tool_id="call_a", name="finish", input_data={}),
            tool_use_block(tool_id="call_b", name="scan", input_data={}),
        ],
    }
    repaired = repair_tool_message_pairs([assistant, tool_message("call_a", "完成")])
    assert len(repaired) == 2
    blocks = normalize_content(repaired[0]["content"])
    tool_use_ids = [b.get("id") for b in blocks if b.get("type") == "tool_use"]
    assert tool_use_ids == ["call_a"]
    assert any(
        b.get("type") == "text" and "[行动]" in str(b.get("text", ""))
        for b in blocks
    )


def test_user_embedded_tool_result_becomes_text_in_wire():
    """user 内嵌 orphan tool_result 应降级为 text。"""
    canonical = [
        {"role": "assistant", "content": [text_block("先写剧本")]},
        {
            "role": "user",
            "content": [
                text_block("任务简报"),
                tool_result_block(tool_use_id="call_orphan", content="失败"),
            ],
        },
    ]
    wire = canonical_to_anthropic_messages(canonical)
    assert_wire_tool_pairs_valid(wire)
    user_blocks = wire[-1]["content"]
    assert all(b.get("type") != "tool_result" for b in user_blocks)
    assert any("[观察]" in str(b.get("text", "")) for b in user_blocks if b.get("type") == "text")


def test_repair_orphan_tool_to_observation_text():
    repaired = repair_tool_message_pairs([tool_message("call_orphan", "执行失败")])
    assert len(repaired) == 1
    assert repaired[0]["role"] == "assistant"
    assert "[观察]" in message_content_text(repaired[0]["content"])
    assert "执行失败" in message_content_text(repaired[0]["content"])


def test_split_for_compression_keeps_tool_turn_atomic():
    messages: list[dict] = [
        {"role": "user", "content": [text_block("诉求")]},
        {
            "role": "assistant",
            "content": [tool_use_block(tool_id="call_a", name="finish", input_data={})],
        },
        tool_message("call_a", "完成"),
    ]
    for i in range(6):
        messages.append({"role": "assistant", "content": [text_block(f"填充{i}")]} )

    kept, older = split_messages_for_compression(messages, keep=2, pin_first_user=True)
    assert older
    roles = [m.get("role") for m in kept]
    if "tool" in roles:
        tool_index = roles.index("tool")
        assert kept[tool_index - 1]["role"] == "assistant"


def test_build_master_react_chat_history_from_store():
    store = ConversationStore()
    store.add_user_message("conv1", "p1", "s1", "做短片")
    store.add_orphan_observation("conv1", "p1", "s1", "工具返回计划", channel="master")

    history = build_master_react_chat_history(store, "conv1")
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"][0]["type"] == "text"
    assert history[1]["content"][0]["text"].startswith("[观察]")


def test_build_master_react_chat_history_keeps_long_history():
    """build_master_react_chat_history 不做主动 snippet 截断。"""
    store = ConversationStore()
    for i in range(20):
        store.add_user_message("conv1", "p1", "s1", f"消息{i}")
    history = build_master_react_chat_history(store, "conv1")
    assert len(history) == 20


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


def test_build_llm_request_history_only_without_turn_user():
    history = [
        {"role": "user", "content": [text_block("你好")]},
        {"role": "assistant", "content": [text_block("收到")]},
    ]
    req = build_llm_request(
        system_prompt="你是主编排",
        history=history,
    )
    assert req.system == "你是主编排"
    assert len(req.messages) == 2
    assert req.messages[-1]["content"] == [text_block("收到")]


def test_extract_react_state_json_from_system():
    state = {"available_actions": ["finish"], "completed_actions": ["无"]}
    system = f"协议\n\n{MASTER_STATE_HEADER}\n{json.dumps(state, ensure_ascii=False)}"
    parsed = extract_react_state_json(
        [{"role": "system", "content": [text_block(system)]}]
    )
    assert parsed == state


def test_extract_react_state_json_with_hint_before_instructions():
    state = {
        "available_actions": ["delegate_agent", "finish"],
        "completed_actions": ["无"],
        "next_actions": ["delegate_agent"],
    }
    hint = "已完成：无；建议下一步：delegate_agent。action 必须且只能从 available_actions 中选择。"
    system = (
        f"协议\n\n{MASTER_STATE_HEADER}\n"
        f"{json.dumps(state, ensure_ascii=False)}\n\n{hint}\n\n{MASTER_STATE_INSTRUCTIONS}"
    )
    parsed = extract_react_state_json(
        [{"role": "system", "content": [text_block(system)]}]
    )
    assert parsed == state


def test_build_llm_request_assembles_system_history_turn():
    history = [
        {"role": "user", "content": [text_block("你好")]},
        {"role": "assistant", "content": [text_block("收到")]},
    ]
    req = build_llm_request(
        system_prompt="你是助手",
        history=history,
        turn_user='{"available_actions": ["finish"]}',
    )
    assert req.system == "你是助手"
    assert len(req.messages) == 3
    assert req.messages[-1]["role"] == "user"
    assert last_user_content(req) == '{"available_actions": ["finish"]}'


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


def test_extract_react_state_json_from_llm_request():
    state = {"available_actions": ["finish"]}
    req = build_llm_request(
        system_prompt=f"{MASTER_STATE_HEADER}\n{json.dumps(state)}",
        history=[{"role": "user", "content": [text_block("hi")]}],
    )
    assert extract_react_state_json(req) == state


def test_extract_react_state_json_from_turn_user():
    state = {"available_actions": ["delegate_agent", "finish"], "completed_actions": ["无"]}
    turn = f"{MASTER_STATE_HEADER}\n{json.dumps(state, ensure_ascii=False)}"
    req = build_llm_request(
        system_prompt="静态协议与角色",
        history=[{"role": "user", "content": [text_block("用户诉求")]}],
        turn_user=turn,
    )
    assert extract_react_state_json(req) == state
    assert REACT_STATE_HEADER not in req.system


def test_add_react_turn_batch_wires_multi_tool_pairs():
    """同轮多 tool_use + tool 消息应被 repair 保留完整配对。"""
    store = ConversationStore()
    store.add_react_turn_batch(
        "conv_batch_wire",
        "p1",
        "s1",
        thought="批量创建",
        calls=[
            ("call_a", "create_character", {"asset_name": "Alice"}, "已创建 Alice"),
            ("call_b", "create_prop", {"asset_name": "Sword"}, "已创建 Sword"),
        ],
        channel="agent",
        agent_name="script_agent",
    )
    history = build_agent_react_chat_history(store, "conv_batch_wire", "script_agent")
    assistant = next(m for m in history if m["role"] == "assistant")
    blocks = normalize_content(assistant["content"])
    tool_use_ids = [b.get("id") for b in blocks if b.get("type") == "tool_use"]
    assert tool_use_ids == ["call_a", "call_b"]
    tool_msgs = [m for m in history if m.get("role") == "tool"]
    assert {m.get("tool_call_id") for m in tool_msgs} == {"call_a", "call_b"}
    repaired = repair_tool_message_pairs(history)
    assert len([m for m in repaired if m.get("role") == "tool"]) == 2
