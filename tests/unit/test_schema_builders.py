"""action input_schema 构建回归测试。"""

import json

from core.llm.prompt.tools.schema_builders import (
    _collect_dangling_def_refs,
    build_shots_array_schema,
    build_video_plan_shot_schema,
)
from core.llm.tools.storyboard.schemas import STORYBOARD_SCHEMAS


def test_video_plan_shot_schema_has_no_shot_detail_ref():
    """分镜 shot schema 不应含 shot_detail 悬空 $ref。"""
    schema = build_video_plan_shot_schema()
    dumped = json.dumps(schema, ensure_ascii=False)
    assert "dict" not in dumped
    assert "$ref" not in dumped
    assert "shot_detail" not in schema.get("properties", {})


def test_shots_array_schema_has_no_dangling_refs():
    """镜头数组 schema 无悬空 $defs 引用。"""
    schema = build_shots_array_schema()
    assert _collect_dangling_def_refs(schema) == []
    assert "$ref" not in json.dumps(schema)


def test_persist_plan_schema_has_no_dangling_refs():
    """persist_plan input_schema 可安全注册为 LLM tool。"""
    schema = STORYBOARD_SCHEMAS["persist_plan"]
    assert _collect_dangling_def_refs(schema) == []
    assert "dict" not in json.dumps(schema)


def test_create_shots_schema_has_no_dangling_refs():
    """create_shots input_schema 无悬空 $ref。"""
    schema = STORYBOARD_SCHEMAS["create_shots"]
    assert _collect_dangling_def_refs(schema) == []
