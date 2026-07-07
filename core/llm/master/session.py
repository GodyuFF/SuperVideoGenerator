"""主编排 ReAct 会话：子 Agent 委派与工具行动空间。"""

from dataclasses import dataclass, field
from typing import Any

from core.llm.tools.shared.agent_tools import ASK_USER_QUESTION_ACTION
from core.llm.models import ReActAgentInfo, ReActToolInfo
from core.models.entities import ExecutionMode, GenerationMode, VideoStyleMode
from core.llm.prompt.registry import PromptProfile, get_agent_role_prompt
from core.llm.master.actions import ACTION_TO_STEP, pipeline_for_style, STEP_META
from core.llm.master.tools import build_master_tools


@dataclass
class ReActSubAgentSpec:
    """可委派的子 Agent（主编排通过 delegate_* 行动调用）。"""

    delegate_action: str
    agent_name: str
    display_name: str
    description: str
    step_type: str


@dataclass
class ReActSession:
    """
    单次对话的 ReAct 会话上下文。

    LLM 根据本结构选择委派子 Agent（delegate_*）、调用工具（tool_*）或 finish。
    """

    conversation_id: str
    agent_name: str
    agent: ReActAgentInfo
    tools: list[ReActToolInfo]
    sub_agents: list[ReActSubAgentSpec]
    project_id: str
    script_id: str
    task_brief: str
    style_mode: VideoStyleMode
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
        return action.startswith("delegate_")

    def is_tool_action(self, action: str) -> bool:
        return action.startswith("tool_")

    def step_type_for_delegate(self, action: str) -> str | None:
        return ACTION_TO_STEP.get(action)

    def available_actions(self) -> list[str]:
        """子 Agent 委派 + 工具 + finish（含已完成 delegate，由 completed_actions 标记）。"""
        pipeline = pipeline_for_style(self.style_mode)
        tool_actions = [t.action_name for t in self.tools]
        actions = list(pipeline) + tool_actions + ["finish"]
        if str(self.extra.get("execution_mode", "")) != ExecutionMode.GOAL.value:
            actions.append(ASK_USER_QUESTION_ACTION)
        return actions

    def next_actions(self) -> list[str]:
        """尚未完成的 delegate；结合 pipeline_progress 与续跑意图排序，供 LLM 按用户目标选择。"""
        pipeline = pipeline_for_style(self.style_mode)
        pending = [
            a
            for a in pipeline
            if ACTION_TO_STEP.get(a) not in self.completed_step_types
        ]
        resume_target = str(self.extra.get("user_resume_target", "") or "").strip()
        if resume_target:
            delegate = next(
                (k for k, v in ACTION_TO_STEP.items() if v == resume_target),
                None,
            )
            progress = self.extra.get("pipeline_progress") or {}
            if delegate and delegate in pending:
                if resume_target == "edit_compose" and progress.get(
                    "ready_for_edit_compose"
                ):
                    rest = [a for a in pending if a != delegate]
                    return [delegate, *rest]
                if resume_target != "edit_compose":
                    rest = [a for a in pending if a != delegate]
                    return [delegate, *rest]
        return pending

    def completed_labels(self) -> list[str]:
        step_to_action = {v: k for k, v in ACTION_TO_STEP.items()}
        labels = [
            step_to_action.get(step, step) for step in sorted(self.completed_step_types)
        ]
        for t in sorted(self.completed_tools):
            labels.append(f"tool:{t}")
        return labels


def build_master_sub_agents() -> list[ReActSubAgentSpec]:
    """主编排可委派的全部子 Agent 定义。"""
    result: list[ReActSubAgentSpec] = []
    for step_type, meta in STEP_META.items():
        delegate = next(
            (k for k, v in ACTION_TO_STEP.items() if v == step_type),
            None,
        )
        if not delegate:
            continue
        result.append(
            ReActSubAgentSpec(
                delegate_action=delegate,
                agent_name=meta["agent"],
                display_name=meta["title"],
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
    style_mode: VideoStyleMode,
    generation_mode: Any,
    *,
    execution_mode: ExecutionMode = ExecutionMode.INTERACTIVE,
    agent_name: str = "super_video_master",
    agent_display_name: str = "超级视频大师",
) -> ReActSession:
    """对话开始时创建主编排 ReAct 会话。"""
    preview = user_message.replace("\n", " ")
    if len(preview) > 80:
        preview = preview[:80] + "…"
    gm = (
        generation_mode.value
        if hasattr(generation_mode, "value")
        else str(generation_mode)
    )
    return ReActSession(
        conversation_id=conversation_id,
        agent_name=agent_name,
        agent=ReActAgentInfo(
            name=agent_name,
            display_name=agent_display_name,
            description=get_agent_role_prompt(agent_name, PromptProfile.DEFAULT),
        ),
        tools=build_master_tools(),
        sub_agents=build_master_sub_agents(),
        project_id=project_id,
        script_id=script_id,
        task_brief=(
            "根据用户诉求与本对话进度，选择委派子 Agent（delegate_*）、调用工具（tool_*）或 finish。"
            "Store 已有素材见 pipeline_progress；新对话须据 user_message 重新规划，"
            "勿将 inferred_completed_steps 等同于 completed_actions。"
            "若用户指定从某阶段继续，以用户消息为准并结合 pipeline_progress 校验依赖。"
        ),
        style_mode=style_mode,
        user_summary=preview,
        extra={
            "style_mode": style_mode.value,
            "generation_mode": gm,
            "execution_mode": execution_mode.value,
        },
    )
