"""提示词注册表：从 core/prompt 目录加载规则与各 Agent 固定提示词。"""

import re
from enum import Enum

from pydantic import BaseModel

from core.prompt.loader import load_required, load_text


class PromptProfile(str, Enum):
    """提示词配置模式，与视频风格模式对齐并可独立选用。"""

    DEFAULT = "default"
    DYNAMIC_IMAGE = "dynamic_image"
    AI_VIDEO = "ai_video"


class AgentPromptBundle(BaseModel):
    """单个 Agent 在某模式下的提示词集合。"""

    role_prompt: str
    action_hint: str = ""


_PROFILE_FILE_SUFFIX = {
    PromptProfile.DEFAULT: "default",
    PromptProfile.DYNAMIC_IMAGE: "dynamic_image",
    PromptProfile.AI_VIDEO: "ai_video",
}

_AGENT_NAMES = (
    "super_video_master",
    "script_agent",
    "image_agent",
    "storyboard_agent",
    "video_agent",
    "tts_agent",
    "editing_agent",
)

_PROFILE_LABELS: dict[PromptProfile, str] = {
    PromptProfile.DEFAULT: "默认",
    PromptProfile.DYNAMIC_IMAGE: "动态图片模式",
    PromptProfile.AI_VIDEO: "AI 视频模式",
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
    # 优先使用 JSON 协议（OpenAI 风格），回退 XML
    return load_text("rules/react_json.md") or load_required("rules/react_xml.md")


def get_action_json_system_base() -> str:
    return load_required("rules/action_json.md")


def get_agent_role_prompt(agent_name: str, profile: PromptProfile) -> str:
    suffix = _PROFILE_FILE_SUFFIX[profile]
    text = _load_with_fallback(
        [
            _agent_fixed_path(agent_name, f"role.{suffix}.md"),
            f"agents/{agent_name}/role.{suffix}.md",
        ]
    )
    if text:
        return text
    if profile != PromptProfile.DEFAULT:
        return get_agent_role_prompt(agent_name, PromptProfile.DEFAULT)
    return f"你是 {agent_name}。"


def get_agent_action_hint(agent_name: str, profile: PromptProfile) -> str:
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


def get_agent_actions_prompt(agent_name: str) -> str:
    """Agent 专属行动 JSON 字段说明（固定区）。"""
    return _load_with_fallback(
        [
            _agent_fixed_path(agent_name, "actions.md"),
            f"agents/{agent_name}/actions.md",
        ]
    )


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


def get_agent_bundle(agent_name: str, profile: PromptProfile) -> AgentPromptBundle:
    return AgentPromptBundle(
        role_prompt=get_agent_role_prompt(agent_name, profile),
        action_hint=get_agent_action_hint(agent_name, profile),
    )


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


def list_prompt_profiles() -> list[dict[str, str]]:
    return [{"id": p.value, "label": _PROFILE_LABELS[p]} for p in PromptProfile]
