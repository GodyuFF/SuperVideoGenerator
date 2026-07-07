"""Skill 加载与 / 命令解析。"""

import pytest

from core.llm.prompt.skills import list_skills, load_skill, parse_skill_command


def test_list_skills_includes_thriller():
    ids = {s.id for s in list_skills()}
    assert "thriller" in ids


def test_load_skill_thriller():
    bundle = load_skill("thriller")
    assert bundle is not None
    assert bundle.meta.title
    assert "悬念" in bundle.system_prompt or bundle.system_prompt
    assert bundle.agent_overlays.get("storyboard_agent")


def test_load_unknown_skill():
    assert load_skill("not-a-real-skill") is None


def test_parse_skill_command_with_message():
    skill_id, rest = parse_skill_command("/thriller 做一段悬疑短片")
    assert skill_id == "thriller"
    assert rest == "做一段悬疑短片"


def test_parse_skill_command_alias():
    skill_id, rest = parse_skill_command("/suspense 测试")
    assert skill_id == "thriller"
    assert rest == "测试"


def test_parse_skill_command_no_slash():
    skill_id, rest = parse_skill_command("普通消息")
    assert skill_id is None
    assert rest == "普通消息"


def test_parse_skill_command_unknown_prefix():
    skill_id, rest = parse_skill_command("/unknown-skill hello")
    assert skill_id is None
    assert rest == "/unknown-skill hello"
