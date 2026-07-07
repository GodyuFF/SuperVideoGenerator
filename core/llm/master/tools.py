"""超级视频大师可调用的 ReAct Tools。"""

from typing import Any

from core.llm.models import ReActToolInfo
from core.llm.tools.shared.assets_summary import (
    build_script_assets_payload,
    format_script_assets_summary,
)
from core.llm.tools.web_fetch.tool import handle_read_webpage
from core.store.memory import MemoryStore


class MasterToolExecutor:
    """执行 tool_* 行动并返回 Observation 文本。"""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def execute(
        self,
        tool_action: str,
        script_id: str,
        action_input: dict[str, Any] | None = None,
    ) -> str:
        name = tool_action.removeprefix("tool_")
        if name == "get_plan_summary":
            return self._get_plan_summary(script_id)
        if name == "list_assets":
            return self._list_assets(script_id)
        if name == "read_webpage":
            return self._read_webpage(action_input or {})
        raise ValueError(f"未知工具行动: {tool_action}")

    def _read_webpage(self, action_input: dict[str, Any]) -> str:
        from core.llm.agent.react_core import AgentRunContext

        ctx = AgentRunContext(
            task_brief="",
            work_context={},
            script_id="",
            step_id="",
            agent_name="super_video_master",
        )
        args = dict(action_input)
        if not str(args.get("observation", "")).strip():
            args["observation"] = "读取网页"
        result = handle_read_webpage(self._store, ctx, args)
        return result.observation

    def _get_plan_summary(self, script_id: str) -> str:
        plan = self._store.get_plan(script_id)
        if not plan:
            return "当前尚无计划文档。"
        lines = [f"计划版本 v{plan.version}，目标：{plan.goal}。"]
        if not plan.steps:
            lines.append("步骤列表为空。")
        else:
            for s in plan.steps:
                lines.append(f"- {s.title}（{s.type}）: {s.status.value}")
        return "\n".join(lines)

    def _list_assets(self, script_id: str) -> str:
        try:
            payload = build_script_assets_payload(self._store, script_id)
        except ValueError as exc:
            return str(exc)
        return format_script_assets_summary(payload)


def build_master_tools() -> list[ReActToolInfo]:
    """主编排可调用的工具列表（与 MasterToolExecutor 行动名一致）。"""
    return [
        ReActToolInfo(
            action_name="tool_get_plan_summary",
            name="get_plan_summary",
            description="查询当前计划版本与各步骤执行状态。",
        ),
        ReActToolInfo(
            action_name="tool_list_assets",
            name="list_assets",
            description="查询当前剧本的文字/图片/音频/视频/成片资产清单（含 URL 与可访问性）。",
        ),
        ReActToolInfo(
            action_name="tool_read_webpage",
            name="read_webpage",
            description="读取指定 URL 的网页正文（只读，http/https）。",
        ),
    ]
