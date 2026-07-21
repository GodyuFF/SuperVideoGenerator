"""注册 update_plan（全 Agent）与 replan（主编排）。"""

from __future__ import annotations

from core.llm.tools.plan.handler import handle_replan, handle_update_plan
from core.llm.tools.plan.schemas import REPLAN_SCHEMA, UPDATE_PLAN_SCHEMA
from core.llm.tools.register_helpers import output_schema_for
from core.llm.tools.registry import ToolRegistry
from core.llm.tools.spec import ToolKind, ToolSpec
from core.llm.tools.web_fetch.tool import COMMON_AGENT

MASTER_AGENT = "super_video_master"


def register_plan_tools(registry: ToolRegistry) -> None:
    """注册显式计划跟踪工具。"""
    if not registry.has("update_plan"):
        registry.register(
            ToolSpec(
                name="update_plan",
                logical_name="common.update_plan",
                description=(
                    "回写本轮计划进度：plan_status 与 remaining_plan。"
                    "不提升 PlanDocument.version；结构调整请用主编排 replan。"
                ),
                agent=COMMON_AGENT,
                kind=ToolKind.WRITE_AD_HOC,
                input_schema=dict(UPDATE_PLAN_SCHEMA),
                output_schema=output_schema_for("update_plan"),
                handler=handle_update_plan,
            )
        )
    if not registry.has("replan"):
        registry.register(
            ToolSpec(
                name="replan",
                logical_name="master.replan",
                description=(
                    "结构化重规划：version++、修改/跳过/重置步骤、可选追加步骤。"
                    "重大变更前交互模式应先 ask_user_question（kind=plan_approval）。"
                ),
                agent=MASTER_AGENT,
                kind=ToolKind.WRITE_AD_HOC,
                input_schema=dict(REPLAN_SCHEMA),
                output_schema=output_schema_for("replan"),
                handler=handle_replan,
            )
        )
