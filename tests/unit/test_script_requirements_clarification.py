"""单元测试：剧本需求补全 A2UI 是否弹出的判定。"""

from core.super_video_master.clarification import (
    has_script_duration_context,
    should_request_script_requirements,
)


def test_skip_when_goal_mode():
    """目标模式不弹需求补全。"""
    assert not should_request_script_requirements(
        goal=True,
        style_known=False,
        has_duration_context=False,
        has_existing_script_body=False,
    )


def test_skip_when_existing_script_body():
    """已有剧本文本（重新设计）时跳过空白确认表。"""
    assert not should_request_script_requirements(
        goal=False,
        style_known=False,
        has_duration_context=False,
        has_existing_script_body=True,
    )


def test_skip_when_style_and_duration_known():
    """风格与时长均已知时跳过。"""
    assert not should_request_script_requirements(
        goal=False,
        style_known=True,
        has_duration_context=True,
        has_existing_script_body=False,
    )


def test_ask_when_style_or_duration_missing():
    """风格或时长缺失时需要补全。"""
    assert should_request_script_requirements(
        goal=False,
        style_known=True,
        has_duration_context=False,
        has_existing_script_body=False,
    )
    assert should_request_script_requirements(
        goal=False,
        style_known=False,
        has_duration_context=True,
        has_existing_script_body=False,
    )


def test_duration_context_from_script_duration_sec():
    """剧本 duration_sec 应计为已知时长。"""
    assert has_script_duration_context(
        user_text="重新设计剧本",
        script_duration_sec=60,
        script_style_hints=None,
        requested_hints=None,
    )


def test_duration_context_from_user_keywords():
    """用户消息含时长关键词时视为已知。"""
    assert has_script_duration_context(
        user_text="做个30秒短片",
        script_duration_sec=0,
        script_style_hints=None,
        requested_hints=None,
    )
