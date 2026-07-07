"""单元测试：ReAct 连续重复工具签名守卫。"""

from core.llm.hook.react_guard import (
    ReActLoopGuard,
    action_signature,
    is_consecutive_duplicate_action,
)


def test_action_signature_stable_for_key_order():
    sig_a = action_signature("list_text_assets", {"note": "查资产", "b": 1})
    sig_b = action_signature("list_text_assets", {"b": 1, "note": "查资产"})
    assert sig_a == sig_b


def test_is_consecutive_duplicate_action_detects_back_to_back():
    sig = action_signature("list_text_assets", {"note": "same"})
    assert is_consecutive_duplicate_action(sig, sig)
    assert not is_consecutive_duplicate_action(None, sig)


def test_react_loop_guard_aborts_on_consecutive_identical_call():
    guard = ReActLoopGuard()
    first = guard.record("list_text_assets", {"note": "查"})
    assert first is None
    second = guard.record("list_text_assets", {"note": "查"})
    assert second is not None
    assert "连续相同参数" in second


def test_react_loop_guard_allows_same_call_after_other_action():
    guard = ReActLoopGuard()
    assert guard.record("list_text_assets", {"note": "查"}) is None
    assert guard.record("create_plot", {}) is None
    assert guard.record("list_text_assets", {"note": "查"}) is None


def test_react_loop_guard_allows_different_input():
    guard = ReActLoopGuard()
    assert guard.record("list_text_assets", {"note": "a"}) is None
    assert guard.record("list_text_assets", {"note": "b"}) is None
