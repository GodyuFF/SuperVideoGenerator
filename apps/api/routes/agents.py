"""REST API：Agent 提示词模式与工具元数据。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.api.state import state
from core.agents.prompts import PromptProfile
from core.models.entities import AgentPromptOverride, VideoStyleMode

router = APIRouter(prefix="/api/agents")


class UpdateAgentConfigRequest(BaseModel):
    """更新全局 Agent 提示词模式。"""

    prompt_profiles: dict[str, str] | None = None


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
    style_mode: VideoStyleMode | None = None,
):
    """列出 Agent 定义、生效提示词与工具。"""
    project = None
    if project_id:
        project = state.store.get_project(project_id)
        if not project:
            raise HTTPException(404, "项目不存在")
    agents = state.agent_config.list_agents_public(
        project=project,
        style_mode=style_mode,
    )
    return {
        "available_profiles": state.agent_config.get_public_config()["available_profiles"],
        "agents": agents,
    }


@router.get("/config")
def get_agent_config():
    """获取全局 Agent 提示词模式配置。"""
    return state.agent_config.get_public_config()


@router.patch("/config")
def patch_agent_config(body: UpdateAgentConfigRequest):
    """更新全局 Agent 提示词模式。"""
    try:
        return state.agent_config.update(prompt_profiles=body.prompt_profiles)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.patch("/projects/{project_id}/config")
def patch_project_agent_config(project_id: str, body: UpdateProjectAgentsRequest):
    """更新项目级 Agent 提示词覆盖。"""
    project = state.store.get_project(project_id)
    if not project:
        raise HTTPException(404, "项目不存在")

    for agent_name, patch in body.overrides.items():
        if patch.prompt_profile is not None:
            try:
                PromptProfile(patch.prompt_profile)
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
