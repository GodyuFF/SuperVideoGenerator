"""全局 Agent 配置数据模型（分 Profile 目录 + registry.json）。"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

StyleVideoGenMode = Literal["text2video", "img2video", "keyframes"]


class CustomPromptProfile(BaseModel):
    """用户自定义 PromptProfile。"""

    id: str
    label: str
    based_on: str | None = None


class CustomStyleMode(BaseModel):
    """用户自定义或内置视频风格模式。"""

    id: str
    label: str
    default_prompt_profile: str = "default"
    include_video_gen: bool = False
    builtin: bool = False
    video: list[StyleVideoGenMode] | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_include_video_gen(cls, data: object) -> object:
        """将旧版 include_video_gen 布尔字段迁移为 video 子模式列表。"""
        if not isinstance(data, dict):
            return data
        video = data.get("video")
        if video is None and data.get("include_video_gen"):
            data = dict(data)
            data["video"] = ["text2video", "img2video", "keyframes"]
        return data

    @model_validator(mode="after")
    def _sync_include_video_gen_flag(self) -> "CustomStyleMode":
        """include_video_gen 与 video 列表保持同步（API 兼容）。"""
        object.__setattr__(self, "include_video_gen", bool(self.video))
        return self


class AgentPromptContentOverride(BaseModel):
    """单 Agent 在某 profile 下的提示词覆盖。"""

    role_prompt: str | None = None
    action_hint: str | None = None


class AgentToolOverride(BaseModel):
    """单 Agent 工具白名单或黑名单（exclude 优先）。"""

    include_only: list[str] | None = None
    exclude: list[str] | None = None

    @model_validator(mode="after")
    def _normalize_lists(self) -> "AgentToolOverride":
        if self.include_only is not None:
            self.include_only = [x.strip() for x in self.include_only if x.strip()]
        if self.exclude is not None:
            self.exclude = [x.strip() for x in self.exclude if x.strip()]
        return self


class CustomAgentDefinition(BaseModel):
    """用户自定义 Agent（克隆内置子 Agent 能力）。"""

    id: str
    label: str
    based_on: str


class ProfileWorkspaceData(BaseModel):
    """单个 Profile 工作区配置（存于 profiles/{id}/workspace.json）。"""

    agent_roster: list[str] = Field(default_factory=list)
    custom_agents: list[CustomAgentDefinition] = Field(default_factory=list)
    prompt_content: dict[str, AgentPromptContentOverride] = Field(default_factory=dict)
    tool_overrides: dict[str, AgentToolOverride] = Field(default_factory=dict)


class AgentRegistryData(BaseModel):
    """全局 registry.json：Profile/风格元数据与全局 Agent 映射。"""

    custom_profiles: list[CustomPromptProfile] = Field(default_factory=list)
    style_modes: list[CustomStyleMode] = Field(default_factory=list)
    prompt_profiles: dict[str, str] = Field(default_factory=dict)
    tool_overrides: dict[str, AgentToolOverride] = Field(default_factory=dict)


class AgentConfigData(BaseModel):
    """聚合视图（API 兼容）：由 registry + 各 Profile 工作区组装。"""

    prompt_profiles: dict[str, str] = Field(default_factory=dict)
    custom_profiles: list[CustomPromptProfile] = Field(default_factory=list)
    style_modes: list[CustomStyleMode] = Field(default_factory=list)
    prompt_content: dict[str, dict[str, AgentPromptContentOverride]] = Field(
        default_factory=dict
    )
    tool_overrides: dict[str, AgentToolOverride] = Field(default_factory=dict)
    custom_agents: list[CustomAgentDefinition] = Field(default_factory=list)
    profile_agents: dict[str, list[str]] = Field(default_factory=dict)
    tool_overrides_by_profile: dict[str, dict[str, AgentToolOverride]] = Field(
        default_factory=dict
    )
