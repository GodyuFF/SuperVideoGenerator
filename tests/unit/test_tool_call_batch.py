"""同轮多 tool_calls batch 校验、分流与 observation 合并测试。"""

import pytest

from core.llm.tool_call_batch import (
    merge_batch_observations,
    resolve_batch_execution_mode,
    validate_tool_call_batch,
)


def test_validate_sub_agent_parallel_create_actions():
    """子 Agent 无依赖 create_* 可同轮并行。"""
    mode = validate_tool_call_batch(
        ["create_character", "create_prop", "create_scene"],
        channel="sub_agent",
    )
    assert mode == "parallel"


def test_validate_rejects_delegate_with_other_actions():
    """独占 action 不可与其他 tool 同轮混用。"""
    with pytest.raises(ValueError, match="不可与其他 tool 同轮调用"):
        validate_tool_call_batch(
            ["delegate_agent", "tool_list_assets"],
            channel="master",
        )


def test_validate_master_tool_prefix_parallel():
    """主编排多个 tool_* 同轮并行。"""
    mode = validate_tool_call_batch(
        ["tool_list_assets", "tool_list_projects"],
        channel="master",
    )
    assert mode == "parallel"


def test_validate_non_parallel_safe_becomes_sequential():
    """非白名单组合不再拒绝，改为顺序执行。"""
    mode = validate_tool_call_batch(
        ["create_character", "parse_brief"],
        channel="sub_agent",
    )
    assert mode == "sequential"
    assert (
        resolve_batch_execution_mode(
            ["tool_list_assets", "create_character"],
            channel="master",
        )
        == "sequential"
    )


def test_merge_batch_observations_mixed_success_and_failure():
    """合并并行/顺序结果时成功与失败条目并存。"""
    merged = merge_batch_observations(
        [
            ("create_character", "c1", "已创建角色 Alice"),
            ("create_prop", "c2", RuntimeError("名称冲突")),
        ]
    )
    assert "1. create_character: 已创建角色 Alice" in merged
    assert "2. create_prop: 失败" in merged
    assert "名称冲突" in merged
