"""Agent 全局配置：各 Agent 默认提示词模式（持久化 JSON）。"""

import json
from pathlib import Path
from typing import Any

from core.llm.agent.prompts import AGENT_PROMPT_PROFILES, PromptProfile, list_prompt_profiles
from core.llm.agent.prompt_resolver import resolve_agent_prompts, resolve_prompt_profile
from core.llm.tools.shared.agent_tools import AGENT_TOOLS, ad_hoc_actions, read_actions
from core.models.entities import Project, VideoStyleMode


DEFAULT_PATH = Path("data/agent_config.json")


class AgentConfigManager:
    """管理各 Agent 的全局提示词模式与公开配置 API。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or DEFAULT_PATH
        self._profiles: dict[str, PromptProfile] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for name, val in raw.get("prompt_profiles", {}).items():
            try:
                self._profiles[name] = PromptProfile(str(val))
            except ValueError:
                continue

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "prompt_profiles": {k: v.value for k, v in self._profiles.items()},
        }
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_profile(self, agent_name: str) -> PromptProfile | None:
        return self._profiles.get(agent_name)

    def get_profiles(self) -> dict[str, PromptProfile]:
        return dict(self._profiles)

    def get_public_config(self) -> dict[str, Any]:
        return {
            "prompt_profiles": {
                name: self._profiles[name].value
                for name in self._profiles
            },
            "available_profiles": list_prompt_profiles(),
            "agents": self.list_agents_public(),
        }

    def list_agents_public(
        self,
        *,
        project: Project | None = None,
        style_mode: VideoStyleMode | None = None,
    ) -> list[dict[str, Any]]:
        """列出 Agent 元数据、当前生效提示词与工具。"""
        from core.llm.agent.definitions import AGENT_DEFINITIONS

        items: list[dict[str, Any]] = []
        for name, defn in AGENT_DEFINITIONS.items():
            bundle = resolve_agent_prompts(
                name,
                style_mode=style_mode,
                global_profiles=self._profiles,
                project=project,
            )
            profile = resolve_prompt_profile(
                name,
                style_mode=style_mode,
                global_profiles=self._profiles,
                project=project,
            )
            tools = AGENT_TOOLS.get(name, [])
            items.append(
                {
                    "name": name,
                    "display_name": defn.display_name,
                    "action_pipeline": defn.action_pipeline,
                    "ad_hoc_actions": ad_hoc_actions(name),
                    "read_actions": read_actions(name),
                    "prompt_profile": profile.value if profile else None,
                    "effective_role_prompt": bundle.role_prompt,
                    "action_hint": bundle.action_hint,
                    "tools": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "action": t.action,
                            "read_only": t.read_only,
                        }
                        for t in tools
                    ],
                }
            )
        return items

    def update(
        self,
        prompt_profiles: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if prompt_profiles is not None:
            for name, val in prompt_profiles.items():
                if name not in AGENT_PROMPT_PROFILES:
                    raise ValueError(f"未知 Agent: {name}")
                try:
                    self._profiles[name] = PromptProfile(val)
                except ValueError as e:
                    raise ValueError(f"Agent {name} 无效提示词模式: {val}") from e
        self._save()
        return self.get_public_config()
