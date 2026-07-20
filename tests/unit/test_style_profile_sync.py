"""风格与 PromptProfile 一对一同步测试。"""

import json

import pytest

from core.llm.agent.config_manager import AgentConfigManager, set_agent_config_manager
from core.llm.agent.style_profile_sync import (
    sync_style_profile_pairs,
    validate_style_profile_patch,
)
from core.models.agent_config import AgentRegistryData, CustomPromptProfile, CustomStyleMode
from core.models.entities import VideoStyleMode


def test_sync_creates_profile_for_orphan_style():
    """仅有 style_modes、无 custom_profiles 时自动补齐同名 profile。"""
    registry = AgentRegistryData(
        style_modes=[
            CustomStyleMode(
                id="brand_video",
                label="品牌视频",
                default_prompt_profile="storybook",
                include_video_gen=False,
                builtin=False,
            )
        ],
        custom_profiles=[],
    )
    synced, changed = sync_style_profile_pairs(registry)
    assert changed is True
    assert len(synced.custom_profiles) == 1
    assert synced.custom_profiles[0].id == "brand_video"
    assert synced.style_modes[0].default_prompt_profile == "brand_video"


def test_sync_removes_orphan_custom_profile():
    """无对应 style_mode 的自定义 profile 应被移除。"""
    registry = AgentRegistryData(
        style_modes=[],
        custom_profiles=[
            CustomPromptProfile(id="orphan", label="孤儿", based_on="storybook"),
        ],
    )
    synced, changed = sync_style_profile_pairs(registry)
    assert changed is True
    assert synced.custom_profiles == []


def test_sync_purges_removed_marketing_video():
    """已下线的 marketing_video 风格应从 registry 移除。"""
    registry = AgentRegistryData(
        style_modes=[
            CustomStyleMode(
                id="marketing_video",
                label="营销视频",
                default_prompt_profile="marketing_video",
                include_video_gen=False,
                builtin=False,
            )
        ],
        custom_profiles=[
            CustomPromptProfile(id="marketing_video", label="营销视频", based_on="storybook"),
        ],
        prompt_profiles={"script_agent": "marketing_video"},
    )
    synced, changed = sync_style_profile_pairs(registry)
    assert changed is True
    assert synced.style_modes == []
    assert synced.custom_profiles == []
    assert synced.prompt_profiles["script_agent"] == VideoStyleMode.STORYBOOK.value


def test_validate_rejects_mismatched_default_prompt_profile():
    """PATCH 拒绝 default_prompt_profile 与 style id 不一致。"""
    styles = [
        CustomStyleMode(
            id="foo",
            label="Foo",
            default_prompt_profile="storybook",
            builtin=False,
        )
    ]
    profiles = [CustomPromptProfile(id="foo", label="Foo", based_on="storybook")]
    with pytest.raises(ValueError, match="1:1"):
        validate_style_profile_patch(styles, profiles)


def test_load_purges_marketing_video(tmp_path, monkeypatch):
    """启动加载时自动移除历史 marketing_video 风格。"""
    agents_root = tmp_path / "agents"
    agents_root.mkdir(parents=True)
    registry_path = agents_root / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "style_modes": [
                    {
                        "id": "marketing_video",
                        "label": "营销",
                        "default_prompt_profile": "storybook",
                        "include_video_gen": False,
                        "builtin": False,
                    }
                ],
                "custom_profiles": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SVG_AGENTS_ROOT", str(agents_root))
    set_agent_config_manager(None)
    mgr = AgentConfigManager()
    data = mgr.get_data()
    assert not any(sm.id == "marketing_video" for sm in data.style_modes)
    assert not any(cp.id == "marketing_video" for cp in data.custom_profiles)
    set_agent_config_manager(None)


def test_patch_style_only_auto_syncs_profile(tmp_path, monkeypatch):
    """仅提交 style_modes 时后端 sync 自动补齐同名 custom_profiles。"""
    monkeypatch.setenv("SVG_DATA_ROOT", str(tmp_path / "data"))
    set_agent_config_manager(None)
    mgr = AgentConfigManager()
    mgr.update(
        style_modes=[
            CustomStyleMode(
                id="solo_style",
                label="Solo",
                default_prompt_profile="solo_style",
                builtin=False,
            )
        ],
    )
    data = mgr.get_data()
    assert any(cp.id == "solo_style" for cp in data.custom_profiles)
    assert any(sm.id == "solo_style" for sm in data.style_modes)
    set_agent_config_manager(None)
