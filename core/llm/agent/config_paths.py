"""Agent 配置按 Profile 分目录的持久化路径。"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from core.store.project_paths import resolve_data_root

DEFAULT_PROFILE_ID = "default"
WORKSPACE_FILENAME = "workspace.json"
REGISTRY_FILENAME = "registry.json"


def _builtin_style_helpers():
    """惰性导入，避免 config_paths 与 profile_seed 循环依赖。"""
    from core.llm.agent.profile_seed import is_builtin_style_mode, is_builtin_style_profile

    return is_builtin_style_profile, is_builtin_style_mode


def is_builtin_style_profile(profile_id: str) -> bool:
    """是否为内置视频风格 Profile（可 seed 恢复、不可删除）。"""
    is_profile, _ = _builtin_style_helpers()
    return is_profile(profile_id)


def is_builtin_style_mode(style_id: str) -> bool:
    """是否为内置视频风格 id。"""
    _, is_mode = _builtin_style_helpers()
    return is_mode(style_id)


def resolve_agents_root() -> Path:
    """Agent 配置根目录 data/agents。"""
    override = os.getenv("SVG_AGENTS_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (resolve_data_root() / "agents").resolve()


def resolve_profiles_root() -> Path:
    """Profile 工作区根目录 data/agents/profiles。"""
    return (resolve_agents_root() / "profiles").resolve()


def resolve_registry_path() -> Path:
    """全局 registry.json 路径。"""
    return (resolve_agents_root() / REGISTRY_FILENAME).resolve()


def legacy_monolith_config_path() -> Path:
    """旧版单文件 agent_config.json。"""
    return (resolve_agents_root() / "agent_config.json").resolve()


def legacy_root_config_path() -> Path:
    """更早期 data/agent_config.json。"""
    return (resolve_data_root() / "agent_config.json").resolve()


def safe_profile_dir_name(profile_id: str) -> str:
    """将 Profile id 转为安全的目录名。"""
    pid = re.sub(r"[^\w\-]", "_", str(profile_id or "").strip())
    if not pid:
        raise ValueError("profile id 不能为空")
    return pid


def profile_dir(profile_id: str) -> Path:
    """某 Profile 的工作区目录。"""
    return resolve_profiles_root() / safe_profile_dir_name(profile_id)


def profile_workspace_path(profile_id: str) -> Path:
    """某 Profile 的 workspace.json 路径。"""
    return profile_dir(profile_id) / WORKSPACE_FILENAME


def is_default_profile(profile_id: str) -> bool:
    """是否为受保护的 default Profile。"""
    return safe_profile_dir_name(profile_id) == DEFAULT_PROFILE_ID


def is_profile_deletable(profile_id: str) -> bool:
    """Profile 是否允许删除（default 与内置视频风格不可删）。"""
    return not is_default_profile(profile_id) and not is_builtin_style_profile(profile_id)


def is_profile_editable(profile_id: str) -> bool:
    """Profile 是否允许修改（default 不可改）。"""
    return not is_default_profile(profile_id)


def ensure_agents_layout() -> Path:
    """确保 agents 根目录与 default Profile 目录存在。"""
    root = resolve_agents_root()
    profiles = resolve_profiles_root()
    root.mkdir(parents=True, exist_ok=True)
    profiles.mkdir(parents=True, exist_ok=True)
    default_dir = profile_dir(DEFAULT_PROFILE_ID)
    default_dir.mkdir(parents=True, exist_ok=True)
    if not profile_workspace_path(DEFAULT_PROFILE_ID).is_file():
        profile_workspace_path(DEFAULT_PROFILE_ID).write_text("{}", encoding="utf-8")
    return root


def write_json(path: Path, data: dict) -> None:
    """写入 JSON 文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict:
    """读取 JSON 文件，失败返回空 dict。"""
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def remove_profile_dir(profile_id: str) -> None:
    """删除 Profile 工作区目录。"""
    if is_default_profile(profile_id):
        raise ValueError("default Profile 不可删除")
    if is_builtin_style_profile(profile_id):
        raise ValueError(f"内置风格 Profile 不可删除：{profile_id}")
    path = profile_dir(profile_id)
    if path.exists():
        shutil.rmtree(path)


def ensure_agent_config_layout() -> Path:
    """兼容旧接口：确保 agents 目录布局并返回根路径。"""
    return ensure_agents_layout()


def resolve_agent_config_path() -> Path:
    """兼容旧接口：返回 agents 配置根目录。"""
    override = os.getenv("SVG_AGENT_CONFIG_PATH", "").strip()
    if override:
        path = Path(override).expanduser().resolve()
        if path.suffix == ".json":
            return path.parent
        return path
    agents_override = os.getenv("SVG_AGENTS_ROOT", "").strip()
    if agents_override:
        return Path(agents_override).expanduser().resolve()
    return resolve_agents_root()
