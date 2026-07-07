"""tool_call 占位符检测与 ReAct 纠正重试测试。"""

import json

import pytest

from core.llm.client.tool_calls import ToolCallResult
from core.llm.protocol import parse_react_tool_calls
from core.llm.react_decide import (
    _complete_react_decision,
    _sub_agent_react_hint,
)
from core.llm.tool_call_guard import (
    PlaceholderToolCallError,
    assert_not_placeholder_tool_call,
    is_placeholder_tool_call,
)
from core.llm.model.llm_request import LlmRequest
from core.llm.prompt.builder import filter_available_actions
from core.llm.tools.shared.agent_tools import should_hide_when_completed


def _placeholder_result() -> ToolCallResult:
    return ToolCallResult(
        content="思考中",
        tool_calls=[
            {
                "id": "call_bad",
                "type": "function",
                "function": {
                    "name": "$TOOL_NAME",
                    "arguments": '{"$PARAMETER_NAME": $PARAMETER_VALUE}',
                },
            }
        ],
    )


def test_is_placeholder_tool_call_detects_log_case():
    assert is_placeholder_tool_call(_placeholder_result())


def test_assert_not_placeholder_raises():
    with pytest.raises(PlaceholderToolCallError):
        assert_not_placeholder_tool_call(_placeholder_result())


def test_parse_react_tool_calls_dedupes_json_error():
    result = _placeholder_result()
    with pytest.raises(ValueError, match="无法解析 tool arguments:") as exc:
        parse_react_tool_calls(result)
    assert "LLM 返回非合法 JSON: LLM 返回非合法 JSON" not in str(exc.value)


def test_load_edit_context_hidden_after_completed():
    assert should_hide_when_completed("load_edit_context")
    actions = filter_available_actions(
        ["load_edit_context", "plan_edit_timeline", "finish"],
        ["load_edit_context"],
    )
    assert "load_edit_context" not in actions
    assert "plan_edit_timeline" in actions


def test_editing_agent_hint_after_load():
    hint = _sub_agent_react_hint("editing_agent", ["load_edit_context"])
    assert "plan_edit_timeline" in hint


@pytest.mark.asyncio
async def test_complete_react_decision_retries_on_placeholder():
    calls: list[LlmRequest] = []

    async def fake_complete(request, **kwargs):
        calls.append(request)
        if len(calls) == 1:
            return _placeholder_result()
        return ToolCallResult(
            content="ok",
            tool_calls=[
                {
                    "id": "call_ok",
                    "type": "function",
                    "function": {
                        "name": "finish",
                        "arguments": json.dumps(
                            {
                                "observation": "完成",
                                "plan_status": "结束",
                                "remaining_plan": [],
                            }
                        ),
                    },
                }
            ],
        )

    class FakeClient:
        async def complete_tool_calls(self, request, **kwargs):
            return await fake_complete(request, **kwargs)

    request = LlmRequest(
        system="sys",
        messages=[{"role": "user", "content": "task"}],
    )
    decision = await _complete_react_decision(
        FakeClient(),
        request,
        allowed_actions=["finish"],
        log_context={"agent_name": "editing_agent"},
        summary_prefix="test",
        on_delta=None,
    )
    assert decision.action == "finish"
    assert len(calls) == 2
    assert "占位符" in str(calls[1].messages[-1]["content"])


@pytest.mark.asyncio
async def test_complete_react_decision_fails_after_retry_still_placeholder():
    async def fake_complete(request, **kwargs):
        return _placeholder_result()

    class FakeClient:
        async def complete_tool_calls(self, request, **kwargs):
            return await fake_complete(request, **kwargs)

    request = LlmRequest(
        system="sys",
        messages=[{"role": "user", "content": "task"}],
    )
    with pytest.raises(RuntimeError, match="占位符 tool_call"):
        await _complete_react_decision(
            FakeClient(),
            request,
            allowed_actions=["plan_edit_timeline", "finish"],
            log_context={"agent_name": "editing_agent"},
            summary_prefix="test",
            on_delta=None,
        )
