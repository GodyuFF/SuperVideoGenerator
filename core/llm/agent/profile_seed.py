"""内置风格 Profile 系统 seed 加载与恢复。"""

from __future__ import annotations

from pathlib import Path

from core.llm.agent.config_paths import read_json, safe_profile_dir_name
from core.llm.agent.profile_workspace import default_agent_roster
from core.models.agent_config import ProfileWorkspaceData
from core.models.entities import VideoStyleMode

_SEEDS_ROOT = Path(__file__).resolve().parent / "seeds" / "profiles"

BUILTIN_STYLE_PROFILE_IDS: frozenset[str] = frozenset(
    {
        VideoStyleMode.STORYBOOK.value,
        VideoStyleMode.AI_VIDEO.value,
        VideoStyleMode.FRAME_I2V.value,
    }
)


def builtin_style_profile_ids() -> frozenset[str]:
    """返回内置视频风格对应的 Profile id。"""
    return BUILTIN_STYLE_PROFILE_IDS


def is_builtin_style_profile(profile_id: str) -> bool:
    """是否为内置视频风格 Profile（可 seed 恢复、不可删除）。"""
    pid = safe_profile_dir_name(profile_id)
    return pid in BUILTIN_STYLE_PROFILE_IDS


def is_builtin_style_mode(style_id: str) -> bool:
    """是否为内置视频风格 id。"""
    return is_builtin_style_profile(style_id)


def _seed_path(profile_id: str) -> Path:
    """返回某内置 Profile 的 seed workspace.json 路径。"""
    pid = safe_profile_dir_name(profile_id)
    if pid not in BUILTIN_STYLE_PROFILE_IDS:
        raise ValueError(f"无系统 seed：{profile_id}")
    return _SEEDS_ROOT / pid / "workspace.json"


def load_profile_seed(profile_id: str) -> ProfileWorkspaceData:
    """从仓库 seed 加载内置风格 Profile 出厂工作区。"""
    path = _seed_path(profile_id)
    raw = read_json(path)
    if not raw:
        return ProfileWorkspaceData(agent_roster=default_agent_roster())
    try:
        ws = ProfileWorkspaceData.model_validate(raw)
    except ValueError:
        return ProfileWorkspaceData(agent_roster=default_agent_roster())
    if not ws.agent_roster:
        ws = ws.model_copy(update={"agent_roster": default_agent_roster()})
    return ws
