"""提示词注册表：从 core/llm/prompt 目录加载规则与各 Agent 固定提示词。"""

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel

from core.llm.prompt.loader import load_required, load_text

class PromptProfile(str, Enum):
    """提示词配置模式，与视频风格模式对齐并可独立选用。"""

    DEFAULT = "default"
    STORYBOOK = "storybook"
    AI_VIDEO = "ai_video"
    FRAME_I2V = "frame_i2v"


class AgentPromptBundle(BaseModel):
    """单个 Agent 在某模式下的提示词集合。"""

    role_prompt: str
    action_hint: str = ""


_PROFILE_FILE_SUFFIX = {
    PromptProfile.DEFAULT: "default",
    PromptProfile.STORYBOOK: "storybook",
    PromptProfile.AI_VIDEO: "ai_video",
    PromptProfile.FRAME_I2V: "frame_i2v",
}

_AGENT_NAMES = (
    "super_video_master",
    "script_agent",
    "image_agent",
    "storyboard_agent",
    "storyboard_refine_agent",
    "video_agent",
    "tts_agent",
    "editing_agent",
)

_PROFILE_LABELS: dict[PromptProfile, str] = {
    PromptProfile.DEFAULT: "默认",
    PromptProfile.STORYBOOK: "故事书模式",
    PromptProfile.AI_VIDEO: "AI 视频模式",
    PromptProfile.FRAME_I2V: "画面图生视频",
}


def _agent_fixed_path(agent_name: str, filename: str) -> str:
    return f"agents/{agent_name}/fixed/{filename}"


def _load_with_fallback(paths: list[str]) -> str:
    for path in paths:
        text = load_text(path)
        if text:
            return text
    return ""


def get_react_system_prompt() -> str:
    return load_required("rules/react_tools.md")


def get_action_json_system_base() -> str:
    return load_required("rules/action_tools.md")


def get_action_tools_system_base() -> str:
    return get_action_json_system_base()


def get_agent_role_prompt(
    agent_name: str,
    profile: PromptProfile | str,
    *,
    profile_id: str | None = None,
    config: Any | None = None,
) -> str:
    """加载 Agent role 固定提示词；profile 可为 enum 或 profile id 字符串。"""
    if isinstance(profile, str):
        try:
            profile = PromptProfile(profile)
        except ValueError:
            from core.llm.prompt.profile_registry import PromptProfileRegistry

            disk_id = PromptProfileRegistry.resolve_disk_profile_id(profile, config=config)
            profile = PromptProfile(disk_id)
    suffix = _PROFILE_FILE_SUFFIX[profile]
    text = _load_with_fallback(
        [
            _agent_fixed_path(agent_name, f"role.{suffix}.md"),
            f"agents/{agent_name}/role.{suffix}.md",
        ]
    )
    if text:
        if agent_name == "editing_agent" and profile != PromptProfile.AI_VIDEO:
            caps = load_text(_agent_fixed_path(agent_name, "edit_capabilities.md"))
            if caps:
                text = f"{text.strip()}\n\n{caps.strip()}"
        if agent_name == "super_video_master":
            catalog = load_text(_agent_fixed_path(agent_name, "agents_catalog.md"))
            if catalog:
                if profile_id:
                    from core.llm.agent.agent_registry import filter_agents_catalog

                    catalog = filter_agents_catalog(catalog, profile_id, config=config)
                text = f"{text.strip()}\n\n{catalog.strip()}"
        return text
    if profile != PromptProfile.DEFAULT:
        return get_agent_role_prompt(
            agent_name,
            PromptProfile.DEFAULT,
            profile_id=profile_id,
            config=config,
        )
    return f"你是 {agent_name}。"


def get_agent_action_hint(
    agent_name: str,
    profile: PromptProfile | str,
    *,
    profile_id: str | None = None,
    config: Any | None = None,
) -> str:
    """加载 Agent action hint；profile 可为 enum 或 profile id 字符串。"""
    if isinstance(profile, str):
        try:
            profile = PromptProfile(profile)
        except ValueError:
            from core.llm.prompt.profile_registry import PromptProfileRegistry

            disk_id = PromptProfileRegistry.resolve_disk_profile_id(profile, config=config)
            profile = PromptProfile(disk_id)
    suffix = _PROFILE_FILE_SUFFIX[profile]
    text = _load_with_fallback(
        [
            _agent_fixed_path(agent_name, f"hint.{suffix}.md"),
            f"agents/{agent_name}/hint.{suffix}.md",
        ]
    )
    if text:
        return text
    if profile != PromptProfile.DEFAULT:
        return get_agent_action_hint(agent_name, PromptProfile.DEFAULT)
    return ""



def extract_role_summary(role_prompt: str, max_chars: int = 80) -> str:
    """从 role 固定提示词提取一行摘要（用于 STEP_META 等）。"""
    for line in role_prompt.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        text = re.sub(r"^[-*]\s*", "", stripped)
        if len(text) > max_chars:
            return text[: max_chars - 1] + "…"
        return text
    return role_prompt[:max_chars] if role_prompt else ""


def get_agent_bundle(
    agent_name: str,
    profile: PromptProfile | str,
    *,
    config: Any | None = None,
) -> AgentPromptBundle:
    if config is not None or (isinstance(profile, str) and profile not in {p.value for p in PromptProfile}):
        from core.llm.prompt.profile_registry import PromptProfileRegistry

        profile_id = profile.value if isinstance(profile, PromptProfile) else str(profile)
        return PromptProfileRegistry.get_bundle(agent_name, profile_id, config=config)
    enum_profile = profile if isinstance(profile, PromptProfile) else PromptProfile(profile)
    return AgentPromptBundle(
        role_prompt=get_agent_role_prompt(agent_name, enum_profile),
        action_hint=get_agent_action_hint(agent_name, enum_profile),
    )


def list_prompt_profiles(*, config: Any | None = None) -> list[dict[str, str]]:
    from core.llm.prompt.profile_registry import PromptProfileRegistry

    return [
        {"id": str(p["id"]), "label": str(p["label"])}
        for p in PromptProfileRegistry.list_all_profiles(config=config)
    ]


def build_agent_prompt_profiles() -> dict[str, dict[PromptProfile, AgentPromptBundle]]:
    profiles: dict[str, dict[PromptProfile, AgentPromptBundle]] = {}
    for agent_name in _AGENT_NAMES:
        if agent_name == "super_video_master":
            continue
        agent_profiles: dict[PromptProfile, AgentPromptBundle] = {}
        for profile in PromptProfile:
            bundle = get_agent_bundle(agent_name, profile)
            if bundle.role_prompt or bundle.action_hint:
                agent_profiles[profile] = bundle
        if agent_profiles:
            profiles[agent_name] = agent_profiles
    return profiles


AGENT_PROMPT_PROFILES: dict[str, dict[PromptProfile, AgentPromptBundle]] = (
    build_agent_prompt_profiles()
)


def default_role_prompt(agent_name: str) -> str:
    return get_agent_role_prompt(agent_name, PromptProfile.DEFAULT)


def list_prompt_profiles_legacy() -> list[dict[str, str]]:
    return [{"id": p.value, "label": _PROFILE_LABELS[p]} for p in PromptProfile]


# 兼容旧调用：AGENT_PROMPT_PROFILES 仅含内置 enum
