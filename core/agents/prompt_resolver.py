"""Agent 提示词解析：结合全局配置、项目覆盖与视频风格模式。"""

from core.agents.prompts import (
    AGENT_PROMPT_PROFILES,
    AgentPromptBundle,
    PromptProfile,
    default_role_prompt,
)
from core.models.entities import Project, VideoStyleMode


_STYLE_TO_PROFILE: dict[VideoStyleMode, PromptProfile] = {
    VideoStyleMode.DYNAMIC_IMAGE: PromptProfile.DYNAMIC_IMAGE,
    VideoStyleMode.AI_VIDEO: PromptProfile.AI_VIDEO,
}


def resolve_prompt_profile(
    agent_name: str,
    *,
    style_mode: VideoStyleMode | None = None,
    global_profiles: dict[str, PromptProfile] | None = None,
    project: Project | None = None,
) -> PromptProfile:
    """解析最终使用的提示词模式。"""
    if project:
        override = project.config.agents.overrides.get(agent_name)
        if override and override.prompt_profile:
            try:
                return PromptProfile(override.prompt_profile)
            except ValueError:
                pass

    if global_profiles and agent_name in global_profiles:
        return global_profiles[agent_name]

    if style_mode and style_mode in _STYLE_TO_PROFILE:
        profile = _STYLE_TO_PROFILE[style_mode]
        agent_profiles = AGENT_PROMPT_PROFILES.get(agent_name, {})
        if profile in agent_profiles:
            return profile

    return PromptProfile.DEFAULT


def resolve_agent_prompts(
    agent_name: str,
    *,
    style_mode: VideoStyleMode | None = None,
    global_profiles: dict[str, PromptProfile] | None = None,
    project: Project | None = None,
) -> AgentPromptBundle:
    """返回 role_prompt 与 action_hint；项目可覆盖 role_prompt。"""
    profile = resolve_prompt_profile(
        agent_name,
        style_mode=style_mode,
        global_profiles=global_profiles,
        project=project,
    )

    if project:
        override = project.config.agents.overrides.get(agent_name)
        if override and override.role_prompt:
            base = _bundle_for(agent_name, profile)
            return AgentPromptBundle(
                role_prompt=override.role_prompt,
                action_hint=base.action_hint,
            )

    return _bundle_for(agent_name, profile)


def _bundle_for(agent_name: str, profile: PromptProfile) -> AgentPromptBundle:
    profiles = AGENT_PROMPT_PROFILES.get(agent_name, {})
    if profile in profiles:
        return profiles[profile]
    if PromptProfile.DEFAULT in profiles:
        return profiles[PromptProfile.DEFAULT]
    return AgentPromptBundle(role_prompt=default_role_prompt(agent_name))
