"""超级视频大师可调用的 ReAct Tools。"""

from core.llm.models import ReActToolInfo
from core.store.memory import MemoryStore


class MasterToolExecutor:
    """执行 tool_* 行动并返回 Observation 文本。"""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def execute(self, tool_action: str, script_id: str) -> str:
        name = tool_action.removeprefix("tool_")
        if name == "get_plan_summary":
            return self._get_plan_summary(script_id)
        if name == "list_assets":
            return self._list_assets(script_id)
        raise ValueError(f"未知工具行动: {tool_action}")

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
        assets = self._store.list_assets_for_script(script_id)
        if not assets:
            return "当前尚无产出资产。"
        by_type: dict[str, int] = {}
        for a in assets:
            by_type[a.type.value] = by_type.get(a.type.value, 0) + 1
        parts = [f"{t}: {n} 个" for t, n in sorted(by_type.items())]
        return f"共 {len(assets)} 项资产。类型分布：{', '.join(parts)}。"


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
            description="统计剧本已产出的资产数量与类型。",
        ),
    ]
