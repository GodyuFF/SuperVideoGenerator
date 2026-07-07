"""return_to_master 工具注册。"""

from core.llm.tools.registry import ToolRegistry
from core.llm.tools.shared.return_to_master_handler import handle_return_to_master
from core.llm.tools.shared.return_to_master_schema import RETURN_TO_MASTER_SCHEMA
from core.llm.tools.spec import ToolKind, ToolSpec
from core.llm.tools.web_fetch.tool import COMMON_AGENT


def register_return_to_master_tool(registry: ToolRegistry) -> None:
    if registry.has("return_to_master"):
        return
    registry.register(
        ToolSpec(
            name="return_to_master",
            logical_name="common.return_to_master",
            description=(
                "暂停本子 Agent 执行并将结果交还主编排。"
                "信息缺失、需用户确认或需上游补数据时调用；勿编造 ID。"
            ),
            agent=COMMON_AGENT,
            kind=ToolKind.WRITE_AD_HOC,
            input_schema=dict(RETURN_TO_MASTER_SCHEMA),
            output_schema={"type": "object"},
            handler=handle_return_to_master,
        )
    )
