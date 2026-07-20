"""全局 Agent 配置：registry + 按 Profile 分目录工作区。"""



from __future__ import annotations



import logging

from pathlib import Path

from typing import Any



from core.llm.agent.agent_registry import (

    get_custom_agent,

    is_builtin_agent,

    list_agents_for_profile,

    normalize_agent_roster,

    resolve_display_name,

    resolve_implementation_agent,

    validate_custom_agent_definition,

)

from core.llm.agent.config_paths import (

    DEFAULT_PROFILE_ID,

    ensure_agents_layout,

    is_builtin_style_profile,

    is_profile_deletable,

    is_profile_editable,

    resolve_agents_root,

    resolve_registry_path,

)

from core.llm.agent.definitions import AGENT_DEFINITIONS

from core.llm.agent.profile_workspace import (

    aggregate_config,

    copy_profile_workspace,

    default_agent_roster,

    delete_profile_workspace,

    load_all_storage,

    load_profile_workspace,

    persist_all_storage,

    save_profile_workspace,

    split_config_to_storage,

)

from core.llm.prompt.loader import clear_prompt_cache

from core.llm.prompt.profile_registry import PromptProfileRegistry

from core.llm.prompt.registry import PromptProfile

from core.llm.tools.agent_tool_config import (

    apply_agent_tool_overrides,

    list_agent_tool_names,

    list_configurable_tool_names,

    list_global_configurable_tools,

    list_system_tools,

    resolve_effective_configurable_tools,

    resolve_tool_override,

    split_effective_tools_for_react,

    system_tool_description,

)

from core.llm.tools.tool_taxonomy import lookup_tool_spec, tool_public_view

from core.models.agent_config import (

    AgentConfigData,

    AgentPromptContentOverride,

    AgentRegistryData,

    AgentToolOverride,

    CustomAgentDefinition,

    CustomPromptProfile,

    CustomStyleMode,

    ProfileWorkspaceData,

)



logger = logging.getLogger(__name__)



_MASTER_DISPLAY = "超级视频大师"



_ALL_AGENT_NAMES = (

    "super_video_master",

    "script_agent",

    "image_agent",

    "storyboard_agent",

    "storyboard_refine_agent",

    "video_agent",

    "tts_agent",

    "editing_agent",

)





class AgentConfigManager:

    """读写 data/agents/registry.json 与各 profiles/{id}/workspace.json。"""



    def __init__(self, path: Path | None = None) -> None:

        self._agents_root = path.resolve() if path else resolve_agents_root()

        self._registry = AgentRegistryData()

        self._workspaces: dict[str, ProfileWorkspaceData] = {}

        self._data = AgentConfigData()

        self._load()



    @property

    def config_path(self) -> Path:

        """配置根目录（兼容旧 API 的 config_path 字段）。"""

        return self._agents_root



    @property

    def registry_path(self) -> Path:

        """registry.json 绝对路径。"""

        return resolve_registry_path()



    def _load(self) -> None:

        """从磁盘加载 registry 与各 Profile 工作区。"""

        if self._agents_root != resolve_agents_root():

            ensure_agents_layout()

        else:

            ensure_agents_layout()

        self._registry, self._workspaces = load_all_storage()

        if self._sync_registry_style_profiles():

            persist_all_storage(self._registry, self._workspaces)

        self._rebuild_aggregate()

        if self._sanitize_default_profile():

            persist_all_storage(self._registry, self._workspaces)



    def _rebuild_aggregate(self) -> None:

        """将 registry + workspaces 聚合为内存视图。"""

        self._data = aggregate_config(self._registry, self._workspaces)



    def _persist(self) -> None:

        """拆分聚合数据并写入磁盘。"""

        self._sanitize_default_profile()

        registry, workspaces = split_config_to_storage(self._data)

        self._registry = registry

        self._workspaces = workspaces

        self._workspaces[DEFAULT_PROFILE_ID] = ProfileWorkspaceData()

        persist_all_storage(self._registry, self._workspaces)

        clear_prompt_cache()



    def _sanitize_default_profile(self) -> bool:

        """剥离 default Profile 的工作区覆盖，保持只读基线。"""

        changed = False

        pristine = ProfileWorkspaceData()

        current_ws = self._workspaces.get(DEFAULT_PROFILE_ID, ProfileWorkspaceData())

        if current_ws.model_dump() != pristine.model_dump():

            self._workspaces[DEFAULT_PROFILE_ID] = pristine

            changed = True

        for agent, agent_map in list(self._data.prompt_content.items()):

            if DEFAULT_PROFILE_ID in agent_map:

                del agent_map[DEFAULT_PROFILE_ID]

                changed = True

                if not agent_map:

                    del self._data.prompt_content[agent]

        if DEFAULT_PROFILE_ID in self._data.tool_overrides_by_profile:

            del self._data.tool_overrides_by_profile[DEFAULT_PROFILE_ID]

            changed = True

        if self._data.profile_agents.get(DEFAULT_PROFILE_ID):

            self._data.profile_agents[DEFAULT_PROFILE_ID] = []

            changed = True

        return changed



    def _sync_registry_style_profiles(self) -> bool:

        """同步 style_modes 与 custom_profiles，并补齐自定义风格工作区。"""

        from core.llm.agent.style_profile_sync import custom_style_ids, sync_style_profile_pairs

        synced, changed = sync_style_profile_pairs(self._registry)

        if changed:

            self._registry = synced

        ws_changed = False

        for style_id in custom_style_ids(self._registry):

            if style_id not in self._workspaces:

                copy_profile_workspace(DEFAULT_PROFILE_ID, style_id)

                self._workspaces[style_id] = load_profile_workspace(style_id)

                ws_changed = True

        return changed or ws_changed



    def _assert_no_default_profile_patch(

        self,

        *,

        prompt_content: dict[str, dict[str, AgentPromptContentOverride]] | None = None,

        tool_overrides_by_profile: dict[str, dict[str, AgentToolOverride]] | None = None,

        profile_agents: dict[str, list[str]] | None = None,

    ) -> None:

        """拒绝任何对 default Profile 工作区的写入。"""

        if prompt_content:

            for agent, profiles in prompt_content.items():

                if DEFAULT_PROFILE_ID not in profiles:

                    continue

                existing = self._data.prompt_content.get(agent, {}).get(DEFAULT_PROFILE_ID)

                incoming = profiles[DEFAULT_PROFILE_ID]

                if incoming != existing:

                    raise ValueError("default Profile 配置禁止修改")

        if tool_overrides_by_profile and DEFAULT_PROFILE_ID in tool_overrides_by_profile:

            existing = self._data.tool_overrides_by_profile.get(DEFAULT_PROFILE_ID, {})

            incoming = tool_overrides_by_profile[DEFAULT_PROFILE_ID]

            if incoming != existing:

                raise ValueError("default Profile 配置禁止修改")

        if profile_agents and DEFAULT_PROFILE_ID in profile_agents:

            existing = self._data.profile_agents.get(DEFAULT_PROFILE_ID, [])

            incoming = profile_agents[DEFAULT_PROFILE_ID]

            if incoming != existing:

                raise ValueError("default Profile 配置禁止修改")



    def reload(self) -> AgentConfigData:

        """重新从磁盘加载配置并清空提示词缓存。"""

        self._load()

        clear_prompt_cache()

        logger.info("已重新加载 Agent 配置：%s", self._agents_root)

        return self.get_data()



    def get_data(self) -> AgentConfigData:

        """返回完整聚合配置数据。"""

        return self._data.model_copy(deep=True)



    def get_profile_workspace(self, profile_id: str) -> ProfileWorkspaceData:

        """返回某 Profile 的工作区数据。"""

        return self._workspaces.get(profile_id, ProfileWorkspaceData()).model_copy(deep=True)



    def get_profiles(self) -> dict[str, str]:

        """全局各 Agent 选用的 PromptProfile id。"""

        return dict(self._data.prompt_profiles)



    def get_profile_for_agent(self, agent_name: str) -> str:

        """单 Agent 全局 profile，缺省 default。"""

        return self._data.prompt_profiles.get(agent_name, PromptProfile.DEFAULT.value)



    def _cascade_remove_profile(self, profile_id: str) -> None:

        """删除 Profile 时清理聚合视图中的引用并删除工作区目录。"""

        if is_builtin_style_profile(profile_id):

            raise ValueError(f"内置风格 Profile 不可删除：{profile_id}")

        fallback = PromptProfile.DEFAULT.value

        for cp in self._data.custom_profiles:

            if cp.id == profile_id:

                fallback = cp.based_on or fallback

                break

        for agent, agent_map in list(self._data.prompt_content.items()):

            if profile_id in agent_map:

                del agent_map[profile_id]

                if not agent_map:

                    del self._data.prompt_content[agent]

        for agent, pid in list(self._data.prompt_profiles.items()):

            if pid == profile_id:

                self._data.prompt_profiles[agent] = fallback

        if profile_id in self._data.profile_agents:

            del self._data.profile_agents[profile_id]

        if profile_id in self._data.tool_overrides_by_profile:

            del self._data.tool_overrides_by_profile[profile_id]

        if is_profile_deletable(profile_id):

            delete_profile_workspace(profile_id)

            self._workspaces.pop(profile_id, None)



    def _cascade_remove_custom_agent(self, agent_id: str) -> None:

        """删除自定义 Agent 时清理各 Profile 编排与配置。"""

        self._data.custom_agents = [a for a in self._data.custom_agents if a.id != agent_id]

        for profile_id, ids in list(self._data.profile_agents.items()):

            filtered = [x for x in ids if x != agent_id]

            if filtered:

                self._data.profile_agents[profile_id] = filtered

            else:

                del self._data.profile_agents[profile_id]

        if agent_id in self._data.prompt_content:

            del self._data.prompt_content[agent_id]

        if agent_id in self._data.tool_overrides:

            del self._data.tool_overrides[agent_id]

        for profile_id, agents in list(self._data.tool_overrides_by_profile.items()):

            if agent_id in agents:

                del agents[agent_id]

                if not agents:

                    del self._data.tool_overrides_by_profile[profile_id]

        if agent_id in self._data.prompt_profiles:

            del self._data.prompt_profiles[agent_id]



    def _copy_profile_in_aggregate(self, target_id: str, source_id: str = DEFAULT_PROFILE_ID) -> None:
        """将 source Profile 的聚合配置复制到 target（新建 Profile 时调用）。"""
        for agent, profiles in self._data.prompt_content.items():
            if source_id in profiles:
                self._data.prompt_content.setdefault(agent, {})[target_id] = profiles[
                    source_id
                ].model_copy(deep=True)
        source_tools = self._data.tool_overrides_by_profile.get(source_id, {})
        if source_tools:
            self._data.tool_overrides_by_profile[target_id] = {
                agent: ov.model_copy(deep=True) for agent, ov in source_tools.items()
            }
        self._data.profile_agents[target_id] = list(
            self._data.profile_agents.get(source_id) or default_agent_roster()
        )

    def update(

        self,

        *,

        prompt_profiles: dict[str, str] | None = None,

        custom_profiles: list[CustomPromptProfile] | None = None,

        style_modes: list[CustomStyleMode] | None = None,

        prompt_content: dict[str, dict[str, AgentPromptContentOverride]] | None = None,

        tool_overrides: dict[str, AgentToolOverride] | None = None,

        custom_agents: list[CustomAgentDefinition] | None = None,

        profile_agents: dict[str, list[str]] | None = None,

        tool_overrides_by_profile: dict[str, dict[str, AgentToolOverride]] | None = None,

    ) -> AgentConfigData:

        """批量更新配置字段并持久化到分 Profile 目录。"""

        self._assert_no_default_profile_patch(

            prompt_content=prompt_content,

            tool_overrides_by_profile=tool_overrides_by_profile,

            profile_agents=profile_agents,

        )

        new_profile_ids: set[str] = set()

        from core.llm.agent.style_profile_sync import (

            assert_builtin_style_not_removed,

            custom_style_ids,

            sync_style_profile_pairs,

            validate_style_profile_patch,

        )

        synced_style_modes: list[CustomStyleMode] | None = None

        synced_custom_profiles: list[CustomPromptProfile] | None = None

        if style_modes is not None:

            assert_builtin_style_not_removed(self._registry, style_modes)

        if style_modes is not None or custom_profiles is not None:

            merged_registry = self._registry.model_copy()

            if style_modes is not None:

                merged_registry.style_modes = [

                    m for m in style_modes if not m.builtin

                ]

            if custom_profiles is not None:

                merged_registry.custom_profiles = list(custom_profiles)

            synced_registry, _ = sync_style_profile_pairs(merged_registry)

            synced_style_modes = list(synced_registry.style_modes)

            synced_custom_profiles = list(synced_registry.custom_profiles)

            validate_style_profile_patch(synced_style_modes, synced_custom_profiles)

        old_custom_style_ids = custom_style_ids(self._registry)

        if synced_custom_profiles is not None:

            old_custom_ids = {cp.id for cp in self._data.custom_profiles}

            seen: set[str] = set()

            for cp in synced_custom_profiles:

                if cp.id in seen:

                    raise ValueError(f"重复的 custom profile id: {cp.id}")

                seen.add(cp.id)

                if cp.based_on:

                    PromptProfileRegistry.validate_profile_id(cp.based_on, config=self)

            new_custom_ids = {cp.id for cp in synced_custom_profiles}

            new_profile_ids = new_custom_ids - old_custom_ids

            for removed_id in old_custom_ids - new_custom_ids:

                if is_builtin_style_profile(removed_id):

                    raise ValueError(f"内置风格 Profile 不可删除：{removed_id}")

                self._cascade_remove_profile(removed_id)

            self._data.custom_profiles = list(synced_custom_profiles)

        if synced_style_modes is not None:

            seen_style: set[str] = set()

            for sm in synced_style_modes:

                if sm.id in seen_style:

                    raise ValueError(f"重复的 style_mode id: {sm.id}")

                seen_style.add(sm.id)

                if sm.builtin:

                    raise ValueError(f"不可通过 PATCH 提交内置风格：{sm.id}")

                PromptProfileRegistry.validate_profile_id(sm.default_prompt_profile, config=self)

            new_custom_style_ids = custom_style_ids(

                self._registry.model_copy(update={"style_modes": synced_style_modes})

            )

            for removed_id in old_custom_style_ids - new_custom_style_ids:

                if is_builtin_style_profile(removed_id):

                    raise ValueError(f"内置风格不可删除：{removed_id}")

                self._cascade_remove_profile(removed_id)

            self._data.style_modes = list(synced_style_modes)

        if prompt_profiles is not None:

            for agent, profile in prompt_profiles.items():

                PromptProfileRegistry.validate_profile_id(profile, config=self)

            self._data.prompt_profiles = dict(prompt_profiles)

        if prompt_content is not None:

            for agent, profiles in prompt_content.items():

                for pid in profiles:

                    PromptProfileRegistry.validate_profile_id(pid, config=self)

            self._data.prompt_content = prompt_content

        if tool_overrides is not None:

            self._data.tool_overrides = tool_overrides

        if custom_agents is not None:

            old_agent_ids = {a.id for a in self._data.custom_agents}

            validated: list[CustomAgentDefinition] = []

            seen_agent: set[str] = set()

            for item in custom_agents:

                agent = validate_custom_agent_definition(item)

                if agent.id in seen_agent:

                    raise ValueError(f"重复的 custom agent id: {agent.id}")

                seen_agent.add(agent.id)

                validated.append(agent)

            new_agent_ids = {a.id for a in validated}

            for removed_id in old_agent_ids - new_agent_ids:

                self._cascade_remove_custom_agent(removed_id)

            self._data.custom_agents = validated

        if profile_agents is not None:

            known_custom = {a.id for a in self._data.custom_agents}

            normalized: dict[str, list[str]] = {}

            for profile_id, agent_ids in profile_agents.items():

                PromptProfileRegistry.validate_profile_id(profile_id, config=self)

                normalized[profile_id] = normalize_agent_roster(
                    list(agent_ids),
                    known_custom=known_custom,
                )

            self._data.profile_agents = normalized

        if tool_overrides_by_profile is not None:

            cleaned: dict[str, dict[str, AgentToolOverride]] = {}

            for profile_id, agents in tool_overrides_by_profile.items():

                PromptProfileRegistry.validate_profile_id(profile_id, config=self)

                cleaned[profile_id] = dict(agents)

            self._data.tool_overrides_by_profile = cleaned

        for added_id in new_profile_ids:

            if added_id != DEFAULT_PROFILE_ID:

                self._copy_profile_in_aggregate(added_id)

        self._persist()

        self._rebuild_aggregate()

        return self.get_data()



    def clear_prompt_content(

        self, agent_name: str, profile_id: str

    ) -> AgentConfigData:

        """删除某 agent/profile 的 prompt_content 覆盖。"""

        if not is_profile_editable(profile_id):

            raise ValueError("default Profile 配置禁止修改")

        agent_map = self._data.prompt_content.get(agent_name)

        if agent_map and profile_id in agent_map:

            del agent_map[profile_id]

            if not agent_map:

                del self._data.prompt_content[agent_name]

            self._persist()

            self._rebuild_aggregate()

        return self.get_data()

    def _clear_profile_aggregate_overrides(self, profile_id: str) -> None:
        """清除某 Profile 在聚合视图中的提示词与工具覆盖。"""
        for agent, agent_map in list(self._data.prompt_content.items()):
            if profile_id not in agent_map:
                continue
            del agent_map[profile_id]
            if not agent_map:
                del self._data.prompt_content[agent]
        if profile_id in self._data.tool_overrides_by_profile:
            del self._data.tool_overrides_by_profile[profile_id]

    def _apply_builtin_profile_seed(self, profile_id: str) -> None:
        """将内置风格 Profile 内存与磁盘状态重置为 seed（不持久化）。"""
        from core.llm.agent.profile_seed import is_builtin_style_profile, load_profile_seed

        pid = str(profile_id or "").strip()
        if not is_builtin_style_profile(pid):
            raise ValueError(f"仅内置风格 Profile 可恢复系统默认：{profile_id}")

        old_roster = set(self._data.profile_agents.get(pid, []))
        seed = load_profile_seed(pid)
        save_profile_workspace(pid, seed)
        self._workspaces[pid] = seed.model_copy(deep=True)
        self._clear_profile_aggregate_overrides(pid)
        self._data.profile_agents[pid] = list(seed.agent_roster)

        removed_custom = old_roster - set(seed.agent_roster)
        for agent_id in removed_custom:
            if is_builtin_agent(agent_id):
                continue
            still_used = any(
                agent_id in ids
                for prof, ids in self._data.profile_agents.items()
                if prof != pid
            )
            if not still_used:
                self._data.custom_agents = [
                    a for a in self._data.custom_agents if a.id != agent_id
                ]

    def restore_builtin_profile(self, profile_id: str) -> AgentConfigData:
        """将内置风格 Profile 恢复为仓库 seed 出厂配置。"""
        self._apply_builtin_profile_seed(profile_id)
        self._persist()
        self._rebuild_aggregate()
        return self.get_data()

    def restore_all_builtin_profiles(self) -> AgentConfigData:
        """批量恢复两种内置视频风格 Profile 为系统 seed。"""
        from core.llm.agent.profile_seed import builtin_style_profile_ids

        for pid in sorted(builtin_style_profile_ids()):
            self._apply_builtin_profile_seed(pid)
        self._persist()
        self._rebuild_aggregate()
        return self.get_data()

    def _tool_specs_for_agent(self, agent_name: str) -> list[dict[str, Any]]:

        from core.llm.master.tools import MASTER_TOOL_ACTIONS

        from core.llm.tools import get_tool_registry

        from core.llm.tools.shared.agent_tools import AGENT_TOOLS



        if agent_name == "super_video_master":

            registry = get_tool_registry()

            out: list[dict[str, Any]] = []

            for action in MASTER_TOOL_ACTIONS:

                spec = registry.get(action.removeprefix("tool_")) if action.startswith("tool_") else None

                if spec is None:

                    out.append(

                        {

                            "name": action,

                            "description": action,

                            "action": action,

                            "read_only": action == "tool_read_webpage",

                            "kind": "read" if action == "tool_read_webpage" else "pipeline",

                        }

                    )

                else:

                    out.append(

                        {

                            "name": spec.name,

                            "description": spec.description,

                            "action": action,

                            "read_only": spec.read_only,

                            "kind": spec.kind.value if hasattr(spec.kind, "value") else str(spec.kind),

                        }

                    )

            return out



        tools = AGENT_TOOLS.get(agent_name, [])

        return [

            {

                "name": t.name,

                "description": t.description,

                "action": t.action,

                "read_only": t.read_only,

                "kind": "read" if t.read_only else ("adhoc" if t.ad_hoc else "pipeline"),

            }

            for t in tools

        ]



    def _tool_specs_by_action(self, agent_name: str) -> dict[str, dict[str, Any]]:

        """按 action 名索引工具元数据。"""

        specs: dict[str, dict[str, Any]] = {}

        for spec in self._tool_specs_for_agent(agent_name):

            action = spec.get("action") or spec.get("name")

            if action:

                specs[str(action)] = spec

            specs[str(spec["name"])] = spec

        return specs



    def _pipeline_actions(self, agent_name: str, *, profile_id: str | None = None) -> list[str]:

        impl = resolve_implementation_agent(agent_name, config=self, profile_id=profile_id)

        if impl == "super_video_master":

            from core.llm.master.delegate_tool import DELEGATE_AGENT_ACTION

            return [DELEGATE_AGENT_ACTION]

        defn = AGENT_DEFINITIONS.get(impl)

        return list(defn.action_pipeline) if defn else []



    def _read_actions(self, agent_name: str, *, profile_id: str | None = None) -> list[str]:

        impl = resolve_implementation_agent(agent_name, config=self, profile_id=profile_id)

        if impl == "super_video_master":

            from core.llm.master.tools import MASTER_TOOL_ACTIONS



            return [a for a in MASTER_TOOL_ACTIONS if a.startswith("tool_")]

        defn = AGENT_DEFINITIONS.get(impl)

        return list(defn.read_actions) if defn else []



    def _ad_hoc_actions(self, agent_name: str, *, profile_id: str | None = None) -> list[str]:

        impl = resolve_implementation_agent(agent_name, config=self, profile_id=profile_id)

        if impl == "super_video_master":

            return ["finish", "ask_user_question"]

        defn = AGENT_DEFINITIONS.get(impl)

        return list(defn.ad_hoc_actions) if defn else []



    def _build_agent_public(

        self,

        name: str,

        *,

        profile_id: str,

        project: Any | None = None,

        style_mode: Any | None = None,

    ) -> dict[str, Any]:

        """组装单个 Agent 的 API 视图。"""

        from core.llm.agent.prompt_resolver import resolve_agent_prompts



        impl = resolve_implementation_agent(name, config=self, profile_id=profile_id)

        if project or style_mode is not None:

            bundle = resolve_agent_prompts(

                name,

                style_mode=style_mode,

                global_profiles=self.get_profiles(),

                project=project,

                config=self,

            )

            resolved_profile = profile_id

        else:

            bundle = PromptProfileRegistry.get_bundle(name, profile_id, config=self)

            resolved_profile = profile_id

        override = resolve_tool_override(

            name,

            profile_id=resolved_profile,

            style_mode=str(style_mode) if style_mode is not None else None,

            global_profiles=self.get_profiles(),

            config=self,

        )

        all_tool_names = list_agent_tool_names(impl)
        effective_configurable = resolve_effective_configurable_tools(name, impl, override)
        effective_pipeline, effective_read, effective_adhoc = split_effective_tools_for_react(
            impl, effective_configurable
        )
        preserved = list_system_tools(name)
        effective_all = sorted(set(effective_configurable) | set(preserved))

        custom = get_custom_agent(name, config=self, profile_id=profile_id)

        tool_options: list[dict[str, Any]] = []

        seen_actions: set[str] = set()

        for tool_name in effective_configurable:

            if tool_name in seen_actions:

                continue

            seen_actions.add(tool_name)

            spec = lookup_tool_spec(tool_name)

            kind = "pipeline"

            if spec and spec.read_only:

                kind = "read"

            elif tool_name.startswith("tool_"):

                kind = "read" if tool_name == "tool_read_webpage" else "pipeline"

            tool_options.append(

                tool_public_view(

                    agent_name=impl,

                    action=tool_name,

                    name=tool_name,

                    description=spec.description if spec else tool_name,

                    kind=kind,

                    read_only=bool(spec.read_only) if spec else False,

                    spec=spec,

                )

            )

        system_tools: list[dict[str, Any]] = []

        return {

            "name": name,

            "display_name": resolve_display_name(name, config=self, profile_id=profile_id),

            "builtin": is_builtin_agent(name),

            "based_on": custom.based_on if custom else None,

            "action_pipeline": effective_pipeline,

            "ad_hoc_actions": effective_adhoc,

            "read_actions": self._read_actions(name, profile_id=profile_id),

            "prompt_profile": resolved_profile,

            "effective_role_prompt": bundle.role_prompt,

            "action_hint": bundle.action_hint,

            "tools": self._tool_specs_for_agent(impl),

            "tool_options": tool_options,

            "system_tools": system_tools,

            "all_tools": all_tool_names,

            "effective_tools": effective_all,

        }



    def list_agents_public(

        self,

        *,

        project: Any | None = None,

        style_mode: Any | None = None,

        profile_id: str | None = None,

    ) -> list[dict[str, Any]]:

        """供 API 返回的 Agent 列表（含 super_video_master）。"""

        if profile_id:

            PromptProfileRegistry.validate_profile_id(profile_id, config=self)

            agent_ids = list_agents_for_profile(profile_id, config=self)

            return [

                self._build_agent_public(

                    name,

                    profile_id=profile_id,

                    project=project,

                    style_mode=style_mode,

                )

                for name in agent_ids

            ]



        profiles = self.get_profiles()

        result: list[dict[str, Any]] = []

        for name in _ALL_AGENT_NAMES:

            pid = profiles.get(name, PromptProfile.DEFAULT.value)

            result.append(

                self._build_agent_public(

                    name,

                    profile_id=pid,

                    project=project,

                    style_mode=style_mode,

                )

            )

        return result



    def get_public_config(self) -> dict[str, Any]:

        """兼容旧 API：返回完整全局配置。"""

        return self.to_api_dict()



    def to_api_dict(self) -> dict[str, Any]:

        """完整配置 JSON（供 GET /api/agents/config）。"""

        from core.llm.agent.style_profile_sync import custom_style_ids, removed_style_ids

        data = self.get_data()
        removed = removed_style_ids()
        custom_style_ids_set = custom_style_ids(self._registry)

        return {

            "prompt_profiles": data.prompt_profiles,

            "custom_profiles": [
                cp.model_dump() for cp in data.custom_profiles if cp.id not in removed
            ],

            "style_modes": [
                sm.model_dump()
                for sm in data.style_modes
                if sm.id in custom_style_ids_set and sm.id not in removed
            ],

            "prompt_content": {

                agent: {pid: ov.model_dump() for pid, ov in profiles.items()}

                for agent, profiles in data.prompt_content.items()

            },

            "tool_overrides": {

                agent: ov.model_dump() for agent, ov in data.tool_overrides.items()

            },

            "custom_agents": [a.model_dump() for a in data.custom_agents],

            "profile_agents": data.profile_agents,

            "tool_overrides_by_profile": {

                profile: {agent: ov.model_dump() for agent, ov in agents.items()}

                for profile, agents in data.tool_overrides_by_profile.items()

            },

            "available_profiles": [

                {

                    "id": str(p["id"]),

                    "label": str(p["label"]),

                    "builtin": bool(p.get("builtin", False)),

                    "deletable": bool(p.get("deletable", is_profile_deletable(str(p["id"])))),

                    "editable": bool(p.get("editable", is_profile_editable(str(p["id"])))),

                    "restorable": bool(p.get("restorable", False)),

                }

                for p in PromptProfileRegistry.list_all_profiles(config=self)

            ],

            "config_path": str(self._agents_root),

            "registry_path": str(self.registry_path),

        }



    def get_agent_prompt(

        self, agent_name: str, profile_id: str | None = None

    ) -> dict[str, Any]:

        """返回单 agent/profile 的提示词与来源。"""

        pid = profile_id or self.get_profile_for_agent(agent_name)

        PromptProfileRegistry.validate_profile_id(pid, config=self)

        resolve_implementation_agent(agent_name, config=self, profile_id=pid)

        bundle = PromptProfileRegistry.get_bundle(agent_name, pid, config=self)

        sources = PromptProfileRegistry.get_prompt_sources(agent_name, pid, config=self)

        return {

            "agent": agent_name,

            "profile": pid,

            "role_prompt": bundle.role_prompt,

            "action_hint": bundle.action_hint,

            "source": sources,

        }





_shared_instance: AgentConfigManager | None = None





def get_agent_config_manager(*, reload: bool = False) -> AgentConfigManager:

    """返回进程内共享 AgentConfigManager；reload=True 时从磁盘重新加载。"""

    global _shared_instance

    if _shared_instance is None:

        _shared_instance = AgentConfigManager()

    elif reload:

        _shared_instance.reload()

    return _shared_instance





def set_agent_config_manager(manager: AgentConfigManager | None) -> None:

    """测试或注入时替换共享实例。"""

    global _shared_instance

    _shared_instance = manager





def reload_agent_config_globally() -> AgentConfigManager:

    """从磁盘重载共享 Agent 配置。"""

    return get_agent_config_manager(reload=True)


