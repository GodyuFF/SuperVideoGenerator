"""PromptProfile 注册表：内置 enum + custom_profiles。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.llm.agent.config_paths import is_profile_deletable, is_profile_editable
from core.llm.agent.profile_seed import is_builtin_style_profile
from core.llm.agent.style_profile_sync import removed_style_ids
from core.llm.prompt.registry import (
    AgentPromptBundle,
    PromptProfile,
    _PROFILE_LABELS,
    get_agent_action_hint,
    get_agent_role_prompt,
)
from core.models.agent_config import AgentPromptContentOverride, CustomPromptProfile

if TYPE_CHECKING:
    from core.llm.agent.config_manager import AgentConfigManager


def _config_manager() -> "AgentConfigManager":
    from core.llm.agent.config_manager import get_agent_config_manager

    return get_agent_config_manager()


def _builtin_profile_ids() -> set[str]:
    return {p.value for p in PromptProfile}


def _style_label_for_profile(
    profile_id: str, *, config: "AgentConfigManager | None" = None
) -> str | None:
    """从 StyleModeRegistry 取与视频风格 Tab 一致的显示名。"""
    from core.llm.style.style_mode_registry import StyleModeRegistry

    mode = StyleModeRegistry.get_style_mode(profile_id, config=config)
    return mode.label if mode else None


class PromptProfileRegistry:
    """合并内置与自定义 PromptProfile，并提供 bundle 解析。"""

    @staticmethod
    def list_all_profiles(*, config: "AgentConfigManager | None" = None) -> list[dict[str, str | bool]]:
        """返回全部 profile（id、label、builtin）。"""
        mgr = config or _config_manager()
        data = mgr.get_data()
        builtin = [
            {
                "id": p.value,
                "label": _style_label_for_profile(p.value, config=mgr) or _PROFILE_LABELS[p],
                "builtin": True,
                "deletable": is_profile_deletable(p.value),
                "editable": is_profile_editable(p.value),
                "restorable": is_builtin_style_profile(p.value),
            }
            for p in PromptProfile
        ]
        custom_ids = _builtin_profile_ids()
        removed = removed_style_ids()
        custom = [
            {
                "id": cp.id,
                "label": _style_label_for_profile(cp.id, config=mgr) or cp.label,
                "builtin": False,
                "deletable": is_profile_deletable(cp.id),
                "editable": is_profile_editable(cp.id),
                "restorable": False,
            }
            for cp in data.custom_profiles
            if cp.id not in custom_ids and cp.id not in removed
        ]
        return builtin + custom

    @staticmethod
    def validate_profile_id(profile_id: str, *, config: AgentConfigManager | None = None) -> str:
        """校验 profile id 是否已注册。"""
        pid = str(profile_id or "").strip()
        if not pid:
            raise ValueError("profile id 不能为空")
        known = {str(p["id"]) for p in PromptProfileRegistry.list_all_profiles(config=config)}
        if pid not in known:
            raise ValueError(f"未知 PromptProfile: {pid}")
        return pid

    @staticmethod
    def get_custom_profile(
        profile_id: str, *, config: AgentConfigManager | None = None
    ) -> CustomPromptProfile | None:
        mgr = config or _config_manager()
        for cp in mgr.get_data().custom_profiles:
            if cp.id == profile_id:
                return cp
        return None

    @staticmethod
    def resolve_disk_profile_id(profile_id: str, *, config: AgentConfigManager | None = None) -> str:
        """自定义 profile 回退到 based_on 或 default 以读取磁盘 md。"""
        if profile_id in _builtin_profile_ids():
            return profile_id
        custom = PromptProfileRegistry.get_custom_profile(profile_id, config=config)
        if custom and custom.based_on:
            base = custom.based_on.strip()
            if base in _builtin_profile_ids():
                return base
        return PromptProfile.DEFAULT.value

    @staticmethod
    def get_content_override(
        agent_name: str,
        profile_id: str,
        *,
        config: AgentConfigManager | None = None,
    ) -> AgentPromptContentOverride | None:
        mgr = config or _config_manager()
        agent_map = mgr.get_data().prompt_content.get(agent_name) or {}
        return agent_map.get(profile_id)

    @staticmethod
    def get_bundle(
        agent_name: str,
        profile_id: str,
        *,
        config: AgentConfigManager | None = None,
    ) -> AgentPromptBundle:
        """磁盘 md + based_on 链 + prompt_content 覆盖。"""
        from core.llm.agent.agent_registry import resolve_implementation_agent

        disk_agent = resolve_implementation_agent(agent_name, config=config)
        disk_id = PromptProfileRegistry.resolve_disk_profile_id(profile_id, config=config)
        try:
            enum_profile = PromptProfile(disk_id)
        except ValueError:
            enum_profile = PromptProfile.DEFAULT
        role = get_agent_role_prompt(disk_agent, enum_profile, profile_id=profile_id, config=config)
        hint = get_agent_action_hint(disk_agent, enum_profile, profile_id=profile_id, config=config)
        override = PromptProfileRegistry.get_content_override(agent_name, profile_id, config=config)
        if override:
            if override.role_prompt is not None:
                role = override.role_prompt
            if override.action_hint is not None:
                hint = override.action_hint
        return AgentPromptBundle(role_prompt=role, action_hint=hint)

    @staticmethod
    def get_prompt_sources(
        agent_name: str,
        profile_id: str,
        *,
        config: AgentConfigManager | None = None,
    ) -> dict[str, str]:
        """返回 role/hint 来源标记（file | override）。"""
        override = PromptProfileRegistry.get_content_override(agent_name, profile_id, config=config)
        return {
            "role_prompt": "override" if override and override.role_prompt is not None else "file",
            "action_hint": "override" if override and override.action_hint is not None else "file",
        }
