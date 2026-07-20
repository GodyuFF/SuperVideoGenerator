"""Agent 配置路径与迁移测试。"""

import json

import pytest

from core.llm.agent.config_manager import AgentConfigManager, set_agent_config_manager
from core.llm.agent.config_paths import resolve_agent_config_path
from core.models.agent_config import AgentPromptContentOverride, CustomStyleMode


def test_migrate_legacy_agent_config(tmp_path, monkeypatch):
    """旧 data/agent_config.json 应自动迁移到分 Profile 目录结构。"""
    data_root = tmp_path / "data"
    data_root.mkdir()
    legacy = data_root / "agent_config.json"
    legacy.write_text(
        json.dumps({"prompt_content": {"script_agent": {"default": {"role_prompt": "legacy"}}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SVG_DATA_ROOT", str(data_root))
    monkeypatch.delenv("SVG_AGENT_CONFIG_PATH", raising=False)
    monkeypatch.delenv("SVG_AGENTS_ROOT", raising=False)

    set_agent_config_manager(None)
    mgr = AgentConfigManager()
    registry = data_root / "agents" / "registry.json"
    assert registry.is_file()
    default_ws = data_root / "agents" / "profiles" / "default" / "workspace.json"
    assert default_ws.is_file()
    assert mgr.config_path == (data_root / "agents").resolve()
    prompt = mgr.get_agent_prompt("script_agent", "default")
    assert prompt["source"]["role_prompt"] == "file"


def test_reload_reads_disk_changes(tmp_path, monkeypatch):
    """reload() 应重新读取磁盘上的最新 Profile 工作区。"""
    agents_root = tmp_path / "agents"
    monkeypatch.setenv("SVG_AGENTS_ROOT", str(agents_root))
    set_agent_config_manager(None)
    mgr = AgentConfigManager()
    set_agent_config_manager(mgr)

    ws_path = agents_root / "profiles" / "storybook" / "workspace.json"
    ws_path.parent.mkdir(parents=True, exist_ok=True)
    ws_path.write_text(
        json.dumps(
            {
                "prompt_content": {
                    "script_agent": AgentPromptContentOverride(role_prompt="磁盘更新").model_dump(),
                }
            }
        ),
        encoding="utf-8",
    )
    mgr.reload()
    prompt = mgr.get_agent_prompt("script_agent", "storybook")
    assert prompt["role_prompt"] == "磁盘更新"
    set_agent_config_manager(None)


def test_resolve_agent_config_path_env_override(tmp_path, monkeypatch):
    """SVG_AGENT_CONFIG_PATH 可覆盖 agents 根目录。"""
    custom = tmp_path / "custom" / "my_agents.json"
    monkeypatch.setenv("SVG_AGENT_CONFIG_PATH", str(custom))
    assert resolve_agent_config_path() == custom.parent.resolve()


def test_new_profile_copies_default_workspace(tmp_path, monkeypatch):
    """新建自定义风格 Profile 时从 default 复制空工作区基线。"""
    data_root = tmp_path / "data"
    monkeypatch.setenv("SVG_DATA_ROOT", str(data_root))
    monkeypatch.delenv("SVG_AGENT_CONFIG_PATH", raising=False)
    monkeypatch.delenv("SVG_AGENTS_ROOT", raising=False)
    set_agent_config_manager(None)
    mgr = AgentConfigManager()
    mgr.update(
        style_modes=[
            CustomStyleMode(
                id="brand_style",
                label="Brand",
                default_prompt_profile="brand_style",
                builtin=False,
            )
        ],
    )
    brand_ws = data_root / "agents" / "profiles" / "brand_style" / "workspace.json"
    default_ws = data_root / "agents" / "profiles" / "default" / "workspace.json"
    assert brand_ws.is_file()
    from core.llm.agent.profile_workspace import default_agent_roster

    default_payload = json.loads(default_ws.read_text(encoding="utf-8"))
    brand_payload = json.loads(brand_ws.read_text(encoding="utf-8"))
    assert default_payload.get("agent_roster", []) == []
    assert brand_payload.get("agent_roster") == default_agent_roster()
    set_agent_config_manager(None)


def test_default_profile_not_deletable(tmp_path, monkeypatch):
    """default Profile 工作区不可删除。"""
    agents_root = tmp_path / "agents"
    monkeypatch.setenv("SVG_AGENTS_ROOT", str(agents_root))
    from core.llm.agent.profile_workspace import delete_profile_workspace

    AgentConfigManager()
    with pytest.raises(ValueError, match="default"):
        delete_profile_workspace("default")


def test_builtin_style_profile_not_deletable(tmp_path, monkeypatch):
    """内置视频风格 Profile 工作区不可删除。"""
    agents_root = tmp_path / "agents"
    monkeypatch.setenv("SVG_AGENTS_ROOT", str(agents_root))
    from core.llm.agent.profile_workspace import delete_profile_workspace
    from core.models.entities import VideoStyleMode

    AgentConfigManager()
    with pytest.raises(ValueError, match="内置风格"):
        delete_profile_workspace(VideoStyleMode.STORYBOOK.value)
