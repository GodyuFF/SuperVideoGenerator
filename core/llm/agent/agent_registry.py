"""Agent 注册表：内置编排 Agent 与按 Profile 的自定义 Agent。"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from core.llm.agent.definitions import AGENT_DEFINITIONS
from core.llm.agent.profile_workspace import default_agent_roster, resolve_profile_roster
from core.models.agent_config import CustomAgentDefinition

if TYPE_CHECKING:
    from core.llm.agent.config_manager import AgentConfigManager

# 系统内置 Agent（禁止从 Profile 编排中删除主编排）
BUILTIN_AGENT_IDS: tuple[str, ...] = (
    "super_video_master",
    "script_agent",
    "image_agent",
    "storyboard_agent",
    "storyboard_refine_agent",
    "video_agent",
    "tts_agent",
    "editing_agent",
)

_BUILTIN_SET = frozenset(BUILTIN_AGENT_IDS)

# 可作为自定义 Agent 模板的子 Agent（不含主编排）
CLONABLE_AGENT_IDS: tuple[str, ...] = tuple(
    name for name in BUILTIN_AGENT_IDS if name != "super_video_master"
)

MASTER_AGENT_ID = "super_video_master"

_CATALOG_SECTION_RE = re.compile(r"^##\s+([^\s（(]+)", re.MULTILINE)


def is_builtin_agent(agent_id: str) -> bool:
    """判断是否为系统内置 Agent。"""
    return agent_id in _BUILTIN_SET


def list_custom_agents(
    *,
    config: AgentConfigManager | None = None,
    profile_id: str | None = None,
) -> list[CustomAgentDefinition]:
    """返回自定义 Agent 定义（可按 Profile 过滤）。"""
    from core.llm.agent.config_manager import get_agent_config_manager

    mgr = config or get_agent_config_manager()
    if profile_id:
        return list(mgr.get_profile_workspace(profile_id).custom_agents)
    return list(mgr.get_data().custom_agents)


def get_custom_agent(
    agent_id: str,
    *,
    config: AgentConfigManager | None = None,
    profile_id: str | None = None,
) -> CustomAgentDefinition | None:
    """按 id 查找自定义 Agent；优先在指定 Profile 工作区查找。"""
    if profile_id:
        for item in list_custom_agents(config=config, profile_id=profile_id):
            if item.id == agent_id:
                return item
        return None
    for item in list_custom_agents(config=config):
        if item.id == agent_id:
            return item
    return None


def resolve_implementation_agent(
    agent_id: str,
    *,
    config: AgentConfigManager | None = None,
    profile_id: str | None = None,
) -> str:
    """解析磁盘提示词与工具能力所依据的内置 Agent 名。"""
    if is_builtin_agent(agent_id):
        return agent_id
    custom = get_custom_agent(agent_id, config=config, profile_id=profile_id)
    if not custom and profile_id:
        custom = get_custom_agent(agent_id, config=config)
    if custom and custom.based_on in _BUILTIN_SET:
        return custom.based_on
    raise ValueError(f"未知 Agent: {agent_id}")


def resolve_display_name(
    agent_id: str,
    *,
    config: AgentConfigManager | None = None,
    profile_id: str | None = None,
) -> str:
    """解析 Agent 展示名。"""
    custom = get_custom_agent(agent_id, config=config, profile_id=profile_id)
    if not custom and profile_id:
        custom = get_custom_agent(agent_id, config=config)
    if custom:
        return custom.label
    if agent_id == MASTER_AGENT_ID:
        return "超级视频大师"
    defn = AGENT_DEFINITIONS.get(agent_id)
    if defn:
        return defn.display_name
    raise ValueError(f"未知 Agent: {agent_id}")


def normalize_agent_roster(
    agent_ids: list[str],
    *,
    known_custom: set[str] | frozenset[str],
) -> list[str]:
    """校验并规范化 Profile roster（主编排固定首位）。"""
    ordered: list[str] = []
    seen: set[str] = set()
    if MASTER_AGENT_ID not in agent_ids:
        ordered.append(MASTER_AGENT_ID)
        seen.add(MASTER_AGENT_ID)
    for agent_id in agent_ids:
        aid = str(agent_id).strip()
        if not aid or aid in seen:
            continue
        if aid == MASTER_AGENT_ID:
            if MASTER_AGENT_ID not in ordered:
                ordered.insert(0, MASTER_AGENT_ID)
            seen.add(aid)
            continue
        if is_builtin_agent(aid):
            ordered.append(aid)
            seen.add(aid)
            continue
        if aid not in known_custom:
            raise ValueError(f"Profile 引用了未知自定义 Agent: {aid}")
        ordered.append(aid)
        seen.add(aid)
    if MASTER_AGENT_ID not in ordered:
        ordered.insert(0, MASTER_AGENT_ID)
    return ordered


def list_agents_for_profile(
    profile_id: str, *, config: AgentConfigManager | None = None
) -> list[str]:
    """返回某 Profile 下可见 Agent id 列表（按 roster 配置）。"""
    from core.llm.agent.config_manager import get_agent_config_manager

    mgr = config or get_agent_config_manager()
    ws = mgr.get_profile_workspace(profile_id)
    roster = resolve_profile_roster(ws, profile_id=profile_id)
    seen: set[str] = set()
    ordered: list[str] = []
    for agent_id in roster:
        if agent_id in seen:
            continue
        if agent_id == MASTER_AGENT_ID or is_builtin_agent(agent_id):
            seen.add(agent_id)
            ordered.append(agent_id)
        elif get_custom_agent(agent_id, config=mgr, profile_id=profile_id):
            seen.add(agent_id)
            ordered.append(agent_id)
    if MASTER_AGENT_ID not in ordered:
        ordered.insert(0, MASTER_AGENT_ID)
    return ordered


def resolve_roster_agent_for_step(
    step_type: str,
    profile_id: str,
    *,
    config: AgentConfigManager | None = None,
) -> str | None:
    """按 Profile roster 解析 step 应委派的目标 Agent id。"""
    from core.llm.master.actions import STEP_META
    from core.llm.agent.config_manager import get_agent_config_manager

    meta = STEP_META.get(step_type)
    if not meta:
        return None
    canonical = meta["agent"]
    roster = list_agents_for_profile(profile_id, config=config)
    if canonical in roster:
        return canonical
    mgr = config or get_agent_config_manager()
    for agent_id in roster:
        custom = get_custom_agent(agent_id, config=mgr, profile_id=profile_id)
        if custom and custom.based_on == canonical:
            return agent_id
    return None


def resolve_step_for_roster_agent(
    agent_id: str,
    profile_id: str,
    *,
    config: AgentConfigManager | None = None,
) -> str | None:
    """反向解析：roster agent_id 对应哪个 step_type。"""
    from core.llm.master.actions import STEP_META

    aid = str(agent_id or "").strip()
    if not aid:
        return None
    for step_type in STEP_META:
        resolved = resolve_roster_agent_for_step(
            step_type, profile_id, config=config
        )
        if resolved == aid:
            return step_type
    return None


def delegates_for_roster(
    profile_id: str,
    style_mode: str,
    *,
    config: AgentConfigManager | None = None,
) -> list[str]:
    """返回主编排可用委派行动（统一为 delegate_agent）。"""
    from core.llm.master.delegate_tool import (
        DELEGATE_AGENT_ACTION,
        delegate_agent_available,
    )

    if delegate_agent_available(profile_id, style_mode, config=config):
        return [DELEGATE_AGENT_ACTION]
    return []


def roster_agent_ids_for_catalog(
    profile_id: str,
    *,
    config: AgentConfigManager | None = None,
) -> set[str]:
    """返回 agents_catalog 应保留的 Agent 标识（含 canonical 与 custom id）。"""
    from core.llm.agent.config_manager import get_agent_config_manager

    mgr = config or get_agent_config_manager()
    roster = list_agents_for_profile(profile_id, config=config)
    ids: set[str] = set()
    for agent_id in roster:
        if agent_id == MASTER_AGENT_ID:
            continue
        ids.add(agent_id)
        if is_builtin_agent(agent_id):
            continue
        custom = get_custom_agent(agent_id, config=mgr, profile_id=profile_id)
        if custom:
            ids.add(custom.based_on)
    return ids


def filter_agents_catalog(
    catalog: str,
    profile_id: str,
    *,
    config: AgentConfigManager | None = None,
) -> str:
    """按 Profile roster 过滤 agents_catalog.md 章节。"""
    if not catalog.strip():
        return catalog
    allowed = roster_agent_ids_for_catalog(profile_id, config=config)
    if not allowed:
        return catalog
    lines = catalog.splitlines()
    output: list[str] = []
    include = True
    for line in lines:
        match = _CATALOG_SECTION_RE.match(line)
        if match:
            header_id = match.group(1)
            include = header_id in allowed
        if include:
            output.append(line)
    return "\n".join(output)


def validate_custom_agent_definition(defn: CustomAgentDefinition) -> CustomAgentDefinition:
    """校验自定义 Agent 定义。"""
    agent_id = defn.id.strip()
    if not agent_id:
        raise ValueError("Agent id 不能为空")
    if is_builtin_agent(agent_id):
        raise ValueError(f"不可覆盖内置 Agent id: {agent_id}")
    based_on = (defn.based_on or "").strip()
    if based_on not in CLONABLE_AGENT_IDS:
        raise ValueError(f"无效的 based_on Agent: {based_on}")
    return CustomAgentDefinition(
        id=agent_id,
        label=(defn.label or agent_id).strip(),
        based_on=based_on,
    )
