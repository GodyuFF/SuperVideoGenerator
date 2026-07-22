"""Profile 工作区读写、复制与从旧版单文件迁移。"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from core.llm.agent.config_paths import (
    DEFAULT_PROFILE_ID,
    ensure_agents_layout,
    legacy_monolith_config_path,
    legacy_root_config_path,
    profile_dir,
    profile_workspace_path,
    read_json,
    remove_profile_dir,
    resolve_profiles_root,
    resolve_registry_path,
    write_json,
)
from core.llm.prompt.registry import PromptProfile
from core.models.agent_config import (
    AgentConfigData,
    AgentRegistryData,
    ProfileWorkspaceData,
)

logger = logging.getLogger(__name__)


def _builtin_profile_ids() -> set[str]:
    return {p.value for p in PromptProfile}


def default_agent_roster() -> list[str]:
    """返回默认 Profile Agent 编排（全量内置）。"""
    from core.llm.agent.agent_registry import BUILTIN_AGENT_IDS

    return list(BUILTIN_AGENT_IDS)


def resolve_profile_roster(ws: ProfileWorkspaceData, *, profile_id: str) -> list[str]:
    """解析 Profile 生效 roster；空 roster 回退为全量内置。"""
    if ws.agent_roster:
        return list(ws.agent_roster)
    return default_agent_roster()


def load_registry() -> AgentRegistryData:
    """读取 registry.json。"""
    raw = read_json(resolve_registry_path())
    if not raw:
        return AgentRegistryData()
    try:
        return AgentRegistryData.model_validate(raw)
    except ValueError:
        logger.warning("registry.json 损坏，已回退为空")
        return AgentRegistryData()


def save_registry(data: AgentRegistryData) -> None:
    """写入 registry.json。"""
    write_json(resolve_registry_path(), data.model_dump())


def load_profile_workspace(profile_id: str) -> ProfileWorkspaceData:
    """读取单个 Profile 工作区。"""
    raw = read_json(profile_workspace_path(profile_id))
    if not raw:
        return ProfileWorkspaceData()
    try:
        return ProfileWorkspaceData.model_validate(raw)
    except ValueError:
        logger.warning("Profile 工作区损坏，已回退为空：%s", profile_id)
        return ProfileWorkspaceData()


def save_profile_workspace(profile_id: str, data: ProfileWorkspaceData) -> None:
    """写入单个 Profile 工作区。"""
    profile_dir(profile_id).mkdir(parents=True, exist_ok=True)
    write_json(profile_workspace_path(profile_id), data.model_dump())


def copy_profile_workspace(source_id: str, target_id: str) -> ProfileWorkspaceData:
    """复制 Profile 工作区（新建 Profile 时从 default 复制）。"""
    src = load_profile_workspace(source_id)
    if not src.agent_roster and source_id == DEFAULT_PROFILE_ID:
        copied = ProfileWorkspaceData(agent_roster=default_agent_roster())
    else:
        copied = src.model_copy(deep=True)
        if not copied.agent_roster:
            copied = copied.model_copy(update={"agent_roster": default_agent_roster()})
    save_profile_workspace(target_id, copied)
    return copied


def delete_profile_workspace(profile_id: str) -> None:
    """删除 Profile 工作区目录。"""
    remove_profile_dir(profile_id)


def aggregate_config(
    registry: AgentRegistryData,
    workspaces: dict[str, ProfileWorkspaceData],
) -> AgentConfigData:
    """将 registry + 各 Profile 工作区聚合为 API 兼容结构。"""
    prompt_content: dict[str, dict] = {}
    tool_overrides_by_profile: dict[str, dict] = {}
    skill_allowlists_by_profile: dict[str, dict[str, list[str]]] = {}
    profile_agents: dict[str, list[str]] = {}
    custom_agents_union: dict[str, object] = {}

    for profile_id, ws in workspaces.items():
        roster = resolve_profile_roster(ws, profile_id=profile_id)
        profile_agents[profile_id] = roster
        tool_overrides_by_profile[profile_id] = {
            agent: ov for agent, ov in ws.tool_overrides.items()
        }
        skill_allowlists_by_profile[profile_id] = {
            agent: list(ids) for agent, ids in ws.skill_allowlists.items()
        }
        for agent, ov in ws.prompt_content.items():
            prompt_content.setdefault(agent, {})[profile_id] = ov
        for agent_def in ws.custom_agents:
            custom_agents_union[agent_def.id] = agent_def

    return AgentConfigData(
        prompt_profiles=dict(registry.prompt_profiles),
        custom_profiles=list(registry.custom_profiles),
        style_modes=list(registry.style_modes),
        prompt_content=prompt_content,
        tool_overrides=dict(registry.tool_overrides),
        custom_agents=list(custom_agents_union.values()),
        profile_agents=profile_agents,
        tool_overrides_by_profile=tool_overrides_by_profile,
        skill_allowlists_by_profile=skill_allowlists_by_profile,
    )


def split_config_to_storage(
    data: AgentConfigData,
) -> tuple[AgentRegistryData, dict[str, ProfileWorkspaceData]]:
    """将聚合配置拆分为 registry 与各 Profile 工作区。"""
    registry = AgentRegistryData(
        custom_profiles=list(data.custom_profiles),
        style_modes=list(data.style_modes),
        prompt_profiles=dict(data.prompt_profiles),
        tool_overrides=dict(data.tool_overrides),
    )
    profile_ids: set[str] = set(_builtin_profile_ids())
    profile_ids.add(DEFAULT_PROFILE_ID)
    profile_ids.update(data.profile_agents.keys())
    profile_ids.update(data.tool_overrides_by_profile.keys())
    profile_ids.update(data.skill_allowlists_by_profile.keys())
    for agent_map in data.prompt_content.values():
        profile_ids.update(agent_map.keys())
    for cp in data.custom_profiles:
        profile_ids.add(cp.id)

    agent_defs = {a.id: a for a in data.custom_agents}
    from core.llm.agent.agent_registry import is_builtin_agent

    workspaces: dict[str, ProfileWorkspaceData] = {}
    for profile_id in profile_ids:
        roster = list(data.profile_agents.get(profile_id, []))
        if profile_id == DEFAULT_PROFILE_ID:
            roster = []
        elif not roster:
            roster = default_agent_roster()
        custom_in_roster = [aid for aid in roster if not is_builtin_agent(aid)]
        ws = ProfileWorkspaceData(
            agent_roster=roster,
            custom_agents=[agent_defs[i] for i in custom_in_roster if i in agent_defs],
            prompt_content={
                agent: ov
                for agent, pmap in data.prompt_content.items()
                if profile_id in pmap
                for ov in [pmap[profile_id]]
            },
            tool_overrides=dict(data.tool_overrides_by_profile.get(profile_id, {})),
            skill_allowlists={
                agent: list(ids)
                for agent, ids in (
                    data.skill_allowlists_by_profile.get(profile_id) or {}
                ).items()
            },
        )
        workspaces[profile_id] = ws
    return registry, workspaces


def discover_profile_ids(registry: AgentRegistryData) -> set[str]:
    """合并 registry、style_modes 与磁盘目录中的 Profile id。"""
    ids = set(_builtin_profile_ids())
    ids.add(DEFAULT_PROFILE_ID)
    ids.update(cp.id for cp in registry.custom_profiles)
    ids.update(sm.id for sm in registry.style_modes)
    root = resolve_profiles_root()
    if root.is_dir():
        for child in root.iterdir():
            if child.is_dir() and (child / "workspace.json").is_file():
                ids.add(child.name)
    return ids


def migrate_monolith_if_needed() -> bool:
    """若存在旧版单文件配置，则迁移为分 Profile 目录结构。"""
    if resolve_registry_path().is_file():
        return False
    monolith = legacy_monolith_config_path()
    if not monolith.is_file():
        monolith = legacy_root_config_path()
    if not monolith.is_file():
        return False
    try:
        raw = read_json(monolith)
        data = AgentConfigData.model_validate(raw)
    except ValueError:
        logger.warning("旧版 agent_config 无法解析，跳过迁移：%s", monolith)
        return False
    ensure_agents_layout()
    registry, workspaces = split_config_to_storage(data)
    save_registry(registry)
    for profile_id, ws in workspaces.items():
        save_profile_workspace(profile_id, ws)
    backup = monolith.with_suffix(".json.bak")
    shutil.copy2(monolith, backup)
    logger.info("已从 %s 迁移到分 Profile 目录，备份 %s", monolith, backup)
    return True


def load_all_storage() -> tuple[AgentRegistryData, dict[str, ProfileWorkspaceData]]:
    """加载 registry 与全部 Profile 工作区。"""
    ensure_agents_layout()
    migrate_monolith_if_needed()
    registry = load_registry()
    workspaces: dict[str, ProfileWorkspaceData] = {}
    for profile_id in discover_profile_ids(registry):
        ws = load_profile_workspace(profile_id)
        if profile_id != DEFAULT_PROFILE_ID and not ws.agent_roster:
            ws = ws.model_copy(update={"agent_roster": default_agent_roster()})
        workspaces[profile_id] = ws
    if DEFAULT_PROFILE_ID not in workspaces:
        workspaces[DEFAULT_PROFILE_ID] = ProfileWorkspaceData()
        save_profile_workspace(DEFAULT_PROFILE_ID, workspaces[DEFAULT_PROFILE_ID])
    return registry, workspaces


def persist_all_storage(
    registry: AgentRegistryData,
    workspaces: dict[str, ProfileWorkspaceData],
) -> None:
    """持久化 registry 与全部 Profile 工作区。"""
    save_registry(registry)
    for profile_id, ws in workspaces.items():
        save_profile_workspace(profile_id, ws)
