"""主编排 ReAct 会话：子 Agent 委派与工具行动空间。"""

from dataclasses import dataclass, field
from typing import Any

from core.llm.tools.shared.agent_tools import ASK_USER_QUESTION_ACTION
from core.llm.model.react import ReActAgentInfo, ReActToolInfo
from core.models.entities import ExecutionMode
from core.llm.agent.prompt_resolver import resolve_agent_prompts, resolve_prompt_profile
from core.llm.agent.agent_registry import resolve_display_name, resolve_roster_agent_for_step
from core.llm.master.actions import STEP_META
from core.llm.master.delegate_deps import sort_next_delegate_agent_ids
from core.llm.master.delegate_tool import DELEGATE_AGENT_ACTION, delegate_agent_available
from core.llm.master.tools import build_master_tools


@dataclass
class ReActSubAgentSpec:
    """可委派的子 Agent（主编排通过 delegate_agent 调用）。"""

    agent_name: str
    display_name: str
    description: str
    step_type: str


@dataclass
class ReActSession:
    """
    单次对话的 ReAct 会话上下文。

    LLM 根据本结构选择 delegate_agent(agent_id)、调用工具（tool_*）或 finish。
    """

    conversation_id: str
    agent_name: str
    agent: ReActAgentInfo
    tools: list[ReActToolInfo]
    sub_agents: list[ReActSubAgentSpec]
    project_id: str
    script_id: str
    task_brief: str
    style_mode: str
    user_summary: str = ""
    observations: list[str] = field(default_factory=list)
    completed_step_types: set[str] = field(default_factory=set)
    completed_tools: set[str] = field(default_factory=set)
    iteration: int = 0
    extra: dict[str, Any] = field(default_factory=dict)
    plan_status_history: list[str] = field(default_factory=list)
    last_remaining_plan: list[str] = field(default_factory=list)
    execution_plan: dict[str, Any] = field(default_factory=dict)

    def is_delegate_action(self, action: str) -> bool:
        """判断是否为委派子 Agent 行动。"""
        return action == DELEGATE_AGENT_ACTION

    def is_tool_action(self, action: str) -> bool:
        return action.startswith("tool_")

    def _profile_id(self) -> str:
        """解析当前会话绑定的 PromptProfile id。"""
        pid = str(self.extra.get("prompt_profile_id") or "").strip()
        if pid:
            return pid
        from core.llm.agent.config_manager import get_agent_config_manager

        mgr = get_agent_config_manager()
        return resolve_prompt_profile(
            self.agent_name,
            style_mode=self.style_mode,
            global_profiles=mgr.get_profiles(),
            config=mgr,
        )

    def available_actions(self) -> list[str]:
        """子 Agent 委派 + 工具 + finish（Profile roster 与风格允许时含 delegate_agent）。"""
        from core.extensions.tool_filter import apply_master_tool_filter
        from core.llm.agent.config_manager import get_agent_config_manager
        from core.llm.tools.agent_tool_config import apply_master_tool_overrides, resolve_tool_override

        profile_id = self._profile_id()
        mgr = get_agent_config_manager()
        actions: list[str] = []
        if delegate_agent_available(profile_id, self.style_mode, config=mgr):
            actions.append(DELEGATE_AGENT_ACTION)
        tool_actions = [t.action_name for t in self.tools]
        actions.extend(tool_actions)
        actions.append("update_plan")
        actions.append("replan")
        actions.append("finish")
        if str(self.extra.get("execution_mode", "")) != ExecutionMode.GOAL.value:
            actions.append(ASK_USER_QUESTION_ACTION)
        overlay = self.extra.get("skill_overlay")
        if overlay:
            actions = apply_master_tool_filter(actions, overlay)
        override = resolve_tool_override(
            "super_video_master",
            profile_id=profile_id,
            style_mode=self.style_mode,
            global_profiles=mgr.get_profiles(),
            config=mgr,
        )
        actions = apply_master_tool_overrides(actions, override)
        return actions

    def next_actions(self) -> list[str]:
        """推荐下一步行动；有未完成子 Agent 时返回 delegate_agent。"""
        from core.llm.agent.config_manager import get_agent_config_manager

        profile_id = self._profile_id()
        mgr = get_agent_config_manager()
        readiness = self.extra.get("delegate_readiness") or []
        eligible_ids = [
            str(r["agent_id"])
            for r in readiness
            if r.get("agent_id")
            and not r.get("hard_blockers")
            and r.get("step_type") not in self.completed_step_types
        ]
        pending_ids = sort_next_delegate_agent_ids(eligible_ids, readiness)

        resume_target = str(self.extra.get("user_resume_target", "") or "").strip()
        if resume_target and pending_ids:
            resume_agent = None
            for row in readiness:
                if row.get("step_type") == resume_target:
                    resume_agent = row.get("agent_id")
                    break
            progress = self.extra.get("pipeline_progress") or {}
            if resume_agent and resume_agent in pending_ids:
                if resume_target == "edit_compose" and progress.get(
                    "ready_for_edit_compose"
                ):
                    return [DELEGATE_AGENT_ACTION]
                if resume_target != "edit_compose":
                    return [DELEGATE_AGENT_ACTION]

        if pending_ids and delegate_agent_available(
            profile_id, self.style_mode, config=mgr
        ):
            return [DELEGATE_AGENT_ACTION]
        return []

    def completed_labels(self) -> list[str]:
        """已完成步骤与工具的标签列表。"""
        labels = [f"step:{step}" for step in sorted(self.completed_step_types)]
        for t in sorted(self.completed_tools):
            labels.append(f"tool:{t}")
        return labels


def build_master_sub_agents(
    *,
    profile_id: str | None = None,
    config: Any | None = None,
) -> list[ReActSubAgentSpec]:
    """主编排可委派的子 Agent 定义（按 Profile roster 过滤）。"""
    from core.llm.agent.config_manager import get_agent_config_manager

    mgr = config or get_agent_config_manager()
    pid = profile_id or "default"
    result: list[ReActSubAgentSpec] = []
    for step_type, meta in STEP_META.items():
        target_agent = resolve_roster_agent_for_step(step_type, pid, config=mgr)
        if not target_agent:
            continue
        display = resolve_display_name(target_agent, config=mgr, profile_id=pid)
        result.append(
            ReActSubAgentSpec(
                agent_name=target_agent,
                display_name=display if target_agent != meta["agent"] else meta["title"],
                description=meta["description"],
                step_type=step_type,
            )
        )
    return result


def create_master_react_session(
    conversation_id: str,
    project_id: str,
    script_id: str,
    user_message: str,
    style_mode: str,
    generation_mode: Any,
    *,
    execution_mode: ExecutionMode = ExecutionMode.INTERACTIVE,
    agent_name: str = "super_video_master",
    agent_display_name: str = "超级视频大师",
) -> ReActSession:
    """对话开始时创建主编排 ReAct 会话。"""
    from core.llm.agent.config_manager import get_agent_config_manager

    mgr = get_agent_config_manager()
    profile_id = resolve_prompt_profile(
        agent_name,
        style_mode=style_mode,
        global_profiles=mgr.get_profiles(),
        config=mgr,
    )
    master_bundle = resolve_agent_prompts(
        agent_name,
        style_mode=style_mode,
        global_profiles=mgr.get_profiles(),
        config=mgr,
    )
    preview = user_message.replace("\n", " ")
    if len(preview) > 80:
        preview = preview[:80] + "…"
    gm = (
        generation_mode.value
        if hasattr(generation_mode, "value")
        else str(generation_mode)
    )
    style_id = style_mode.value if hasattr(style_mode, "value") else str(style_mode)
    return ReActSession(
        conversation_id=conversation_id,
        agent_name=agent_name,
        agent=ReActAgentInfo(
            name=agent_name,
            display_name=agent_display_name,
            description=master_bundle.role_prompt,
        ),
        tools=build_master_tools(),
        sub_agents=build_master_sub_agents(profile_id=profile_id, config=mgr),
        project_id=project_id,
        script_id=script_id,
        task_brief=(
            "根据用户诉求与本对话进度，选择 delegate_agent(agent_id) 委派子 Agent、"
            "调用工具（tool_*）或 finish。"
            "Store 已有素材的步骤启动时已记入 completed_actions，勿无故全量重跑；"
            "仅当用户说「全部重做」或明确重做/续跑某步（如重新配音、从剪辑继续）时再开放该步及下游。"
            "若用户指定从某阶段继续，以用户消息为准并结合 pipeline_progress 校验依赖。"
        ),
        style_mode=style_id,
        user_summary=preview,
        extra={
            "style_mode": style_id,
            "generation_mode": gm,
            "execution_mode": execution_mode.value,
            "prompt_profile_id": profile_id,
        },
    )
