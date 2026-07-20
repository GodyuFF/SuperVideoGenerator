"""按项目配置、全局模式与视频风格解析 Agent 提示词。"""

from __future__ import annotations

from typing import Any

from core.llm.prompt.profile_registry import PromptProfileRegistry
from core.llm.prompt.registry import AgentPromptBundle, PromptProfile
from core.llm.style.style_mode_registry import StyleModeRegistry
from core.models.entities import Project, VideoStyleMode


def resolve_prompt_profile(
    agent_name: str,
    *,
    style_mode: VideoStyleMode | str | None = None,
    global_profiles: dict[str, str] | None = None,
    project: Project | None = None,
    config: Any | None = None,
) -> str:
    """解析 Agent 当前应使用的 PromptProfile id。"""
    if project and project.config.agents.overrides.get(agent_name):
        override = project.config.agents.overrides[agent_name]
        if override.prompt_profile:
            return override.prompt_profile

    if global_profiles and agent_name in global_profiles:
        return global_profiles[agent_name]

    if style_mode is not None:
        style_id = style_mode.value if isinstance(style_mode, VideoStyleMode) else str(style_mode)
        return StyleModeRegistry.default_prompt_profile_for_style(style_id, config=config)

    return PromptProfile.DEFAULT.value


def resolve_agent_prompts(
    agent_name: str,
    *,
    style_mode: VideoStyleMode | str | None = None,
    global_profiles: dict[str, str] | None = None,
    project: Project | None = None,
    config: Any | None = None,
) -> AgentPromptBundle:
    """解析 Agent 的 role_prompt 与 action_hint（含全局 prompt_content 覆盖）。"""
    if project and project.config.agents.overrides.get(agent_name):
        override = project.config.agents.overrides[agent_name]
        if override.role_prompt:
            profile_id = resolve_prompt_profile(
                agent_name,
                style_mode=style_mode,
                global_profiles=global_profiles,
                project=project,
                config=config,
            )
            bundle = PromptProfileRegistry.get_bundle(agent_name, profile_id, config=config)
            return AgentPromptBundle(
                role_prompt=override.role_prompt,
                action_hint=bundle.action_hint,
            )

    profile_id = resolve_prompt_profile(
        agent_name,
        style_mode=style_mode,
        global_profiles=global_profiles,
        project=project,
        config=config,
    )
    return PromptProfileRegistry.get_bundle(agent_name, profile_id, config=config)
