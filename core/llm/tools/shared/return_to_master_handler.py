"""return_to_master 工具 handler（全子 Agent 共享）。"""

from __future__ import annotations

from typing import Any

from core.llm.agent.react_core import AgentRunContext
from core.llm.hook.return_to_master import ReturnToMasterError
from core.llm.tools.result import ToolResult
from core.store.memory import MemoryStore


def handle_return_to_master(
    store: MemoryStore, ctx: AgentRunContext, args: dict[str, Any]
) -> ToolResult:
    del store
    reason = str(args.get("reason", "missing_upstream")).strip()
    observation = str(args.get("observation", "")).strip()
    if not observation:
        observation = "子 Agent 请求主编排协调。"
    structured: dict[str, Any] = {
        "agent_name": ctx.agent_name,
        "step_id": ctx.step_id,
        "script_id": ctx.script_id,
    }
    if args.get("missing_items"):
        structured["missing_items"] = args["missing_items"]
    if args.get("suggested_agent_ids"):
        structured["suggested_agent_ids"] = args["suggested_agent_ids"]
    if args.get("resume_hint"):
        structured["resume_hint"] = str(args["resume_hint"]).strip()
    raise ReturnToMasterError(
        "return_to_master",
        observation,
        reason=reason,
        structured=structured,
    )
