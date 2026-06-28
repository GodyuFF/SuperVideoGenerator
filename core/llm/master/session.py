"""主编排 ReAct 会话：子 Agent 委派与工具行动空间。"""

from dataclasses import dataclass, field
from typing import Any

from core.llm.models import ReActAgentInfo, ReActToolInfo
from core.models.entities import VideoStyleMode
from core.prompt.registry import PromptProfile, get_agent_role_prompt
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

    def is_delegate_action(self, action: str) -> bool:
        return action.startswith("delegate_")

    def is_tool_action(self, action: str) -> bool:
        return action.startswith("tool_")

    def step_type_for_delegate(self, action: str) -> str | None:
        return ACTION_TO_STEP.get(action)

    def available_actions(self) -> list[str]:
        """子 Agent 委派 + 工具 + finish。"""
        pipeline = pipeline_for_style(self.style_mode)
        delegates = [
            a
            for a in pipeline
            if ACTION_TO_STEP.get(a) not in self.completed_step_types
        ]
        tool_actions = [t.action_name for t in self.tools]
        return delegates + tool_actions + ["finish"]

    def completed_labels(self) -> list[str]:
        labels = sorted(self.completed_step_types)
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
        task_brief="根据用户诉求与当前进度，选择委派子 Agent（delegate_*）、调用工具（tool_*）或 finish。",
        style_mode=style_mode,
        user_summary=preview,
        extra={
            "style_mode": style_mode.value,
            "generation_mode": gm,
        },
    )
