"""script_agent tools 注册。"""

from core.llm.tools.register_helpers import register_handlers
from core.llm.tools.registry import ToolRegistry
from core.llm.tools.script import handler as script_handler

_SCRIPT_META: dict[str, tuple[str, str, str, str]] = {
    "parse_brief": ("script_agent", "write_pipeline", "script.parse_brief", "解析任务简报并通过 LLM 设计/写入剧本正文"),
    "create_plot": ("script_agent", "write_pipeline", "script.create_plot", "创建剧情文字资产"),
    "create_character": ("script_agent", "write_pipeline", "script.create_character", "创建人物共享资产"),
    "create_scene": ("script_agent", "write_pipeline", "script.create_scene", "创建场景共享资产"),
    "create_prop": ("script_agent", "write_pipeline", "script.create_prop", "创建道具共享资产"),
    "update_script": ("script_agent", "write_ad_hoc", "script.update_script", "更新剧本标题或 Markdown 正文"),
    "update_plot": ("script_agent", "write_ad_hoc", "script.update_plot", "更新剧情文字资产（需 asset_id）"),
    "update_character": ("script_agent", "write_ad_hoc", "script.update_character", "更新人物资产（需 asset_id）"),
    "update_scene": ("script_agent", "write_ad_hoc", "script.update_scene", "更新场景资产（需 asset_id）"),
    "update_prop": ("script_agent", "write_ad_hoc", "script.update_prop", "更新道具资产（需 asset_id）"),
    "delete_plot": ("script_agent", "write_ad_hoc", "script.delete_plot", "删除剧情资产（需 asset_id）"),
    "delete_character": ("script_agent", "write_ad_hoc", "script.delete_character", "删除人物资产（需 asset_id）"),
    "delete_scene": ("script_agent", "write_ad_hoc", "script.delete_scene", "删除场景资产（需 asset_id）"),
    "delete_prop": ("script_agent", "write_ad_hoc", "script.delete_prop", "删除道具资产（需 asset_id）"),
    "list_text_assets": ("script_agent", "read", "script.list_text_assets", "列出剧本相关文字资产及完整 content JSON"),
}

SCRIPT_HANDLERS = {
    "list_text_assets": script_handler.handle_list_text_assets,
    "parse_brief": script_handler.handle_parse_brief,
    "update_script": script_handler.handle_update_script,
    "create_plot": script_handler.handle_create_plot,
    "create_character": script_handler.handle_create_character,
    "create_scene": script_handler.handle_create_scene,
    "create_prop": script_handler.handle_create_prop,
    "update_plot": script_handler.handle_update_plot,
    "update_character": script_handler.handle_update_character,
    "update_scene": script_handler.handle_update_scene,
    "update_prop": script_handler.handle_update_prop,
    "delete_plot": script_handler.handle_delete_plot,
    "delete_character": script_handler.handle_delete_character,
    "delete_scene": script_handler.handle_delete_scene,
    "delete_prop": script_handler.handle_delete_prop,
}


def register_script_tools(registry: ToolRegistry) -> None:
    register_handlers(registry, SCRIPT_HANDLERS, _SCRIPT_META)
