"""REST API：Agent 提示词模式与工具元数据。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.api.state import state
from core.llm.prompt.profile_registry import PromptProfileRegistry
from core.llm.style.style_mode_registry import StyleModeRegistry
from core.models.agent_config import (
    AgentPromptContentOverride,
    AgentToolOverride,
    CustomAgentDefinition,
    CustomPromptProfile,
    CustomStyleMode,
)
from core.models.entities import AgentPromptOverride, VideoStyleMode

router = APIRouter(prefix="/api/agents")


class UpdateAgentConfigRequest(BaseModel):
    """更新全局 Agent 配置。"""

    prompt_profiles: dict[str, str] | None = None
    custom_profiles: list[CustomPromptProfile] | None = None
    style_modes: list[CustomStyleMode] | None = None
    prompt_content: dict[str, dict[str, AgentPromptContentOverride]] | None = None
    tool_overrides: dict[str, AgentToolOverride] | None = None
    custom_agents: list[CustomAgentDefinition] | None = None
    profile_agents: dict[str, list[str]] | None = None
    tool_overrides_by_profile: dict[str, dict[str, AgentToolOverride]] | None = None


class UpdateProjectAgentRequest(BaseModel):
    """更新项目级 Agent 提示词覆盖。"""

    prompt_profile: str | None = None
    role_prompt: str | None = None


class UpdateProjectAgentsRequest(BaseModel):
    """批量更新项目 Agent 配置。"""

    overrides: dict[str, UpdateProjectAgentRequest] = Field(default_factory=dict)


@router.get("")
def list_agents(
    project_id: str | None = None,
    style_mode: str | None = None,
    profile: str | None = None,
):
    """列出 Agent 定义、生效提示词与工具。"""
    project = None
    if project_id:
        project = state.store.get_project(project_id)
        if not project:
            raise HTTPException(404, "项目不存在")
    if style_mode:
        try:
            StyleModeRegistry.validate_style_id(style_mode, config=state.agent_config)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    if profile:
        try:
            PromptProfileRegistry.validate_profile_id(profile, config=state.agent_config)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    agents = state.agent_config.list_agents_public(
        project=project,
        style_mode=style_mode,
        profile_id=profile,
    )
    return {
        "available_profiles": state.agent_config.get_public_config()["available_profiles"],
        "agents": agents,
    }


@router.get("/config")
def get_agent_config():
    """获取全局 Agent 完整配置。"""
    return state.agent_config.get_public_config()


@router.post("/profiles/{profile_id}/restore")
def restore_builtin_profile(profile_id: str):
    """将内置风格 Profile 恢复为系统 seed 出厂配置。"""
    try:
        data = state.agent_config.restore_builtin_profile(profile_id)
        state.reload_agent_config()
        return data.model_dump()
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/config/restore-builtin-profiles")
def restore_all_builtin_profiles():
    """批量恢复 storybook / ai_video 两种内置风格配置。"""
    try:
        data = state.agent_config.restore_all_builtin_profiles()
        state.reload_agent_config()
        return data.model_dump()
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.patch("/config")
def patch_agent_config(body: UpdateAgentConfigRequest):
    """更新全局 Agent 配置。"""
    try:
        data = state.agent_config.update(
            prompt_profiles=body.prompt_profiles,
            custom_profiles=body.custom_profiles,
            style_modes=body.style_modes,
            prompt_content=body.prompt_content,
            tool_overrides=body.tool_overrides,
            custom_agents=body.custom_agents,
            profile_agents=body.profile_agents,
            tool_overrides_by_profile=body.tool_overrides_by_profile,
        )
        state.reload_agent_config()
        return data.model_dump()
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/{agent_name}/prompt")
def get_agent_prompt(agent_name: str, profile: str | None = None):
    """返回指定 Agent/profile 的提示词与来源。"""
    try:
        return state.agent_config.get_agent_prompt(agent_name, profile)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/{agent_name}/prompt/{profile_id}")
def reset_agent_prompt_override(agent_name: str, profile_id: str):
    """删除 prompt_content 覆盖，回退磁盘 md。"""
    try:
        state.agent_config.clear_prompt_content(agent_name, profile_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    state.reload_agent_config()
    return state.agent_config.get_agent_prompt(agent_name, profile_id)


@router.patch("/projects/{project_id}/config")
def patch_project_agent_config(project_id: str, body: UpdateProjectAgentsRequest):
    """更新项目级 Agent 提示词覆盖。"""
    project = state.store.get_project(project_id)
    if not project:
        raise HTTPException(404, "项目不存在")

    for agent_name, patch in body.overrides.items():
        if patch.prompt_profile is not None:
            try:
                PromptProfileRegistry.validate_profile_id(
                    patch.prompt_profile, config=state.agent_config
                )
            except ValueError as e:
                raise HTTPException(400, f"无效提示词模式: {patch.prompt_profile}") from e
        current = project.config.agents.overrides.get(agent_name, AgentPromptOverride())
        if patch.prompt_profile is not None:
            current.prompt_profile = patch.prompt_profile or None
        if patch.role_prompt is not None:
            current.role_prompt = patch.role_prompt.strip() or None
        if current.prompt_profile or current.role_prompt:
            project.config.agents.overrides[agent_name] = current
        elif agent_name in project.config.agents.overrides:
            del project.config.agents.overrides[agent_name]

    state.persist_store()
    return {
        "overrides": {
            k: v.model_dump() for k, v in project.config.agents.overrides.items()
        },
        "agents": state.agent_config.list_agents_public(project=project),
    }
