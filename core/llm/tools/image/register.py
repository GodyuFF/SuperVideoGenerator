"""image_agent tools 注册。"""

from core.llm.tools.image.handler import HANDLERS as IMAGE_HANDLERS
from core.llm.tools.register_helpers import register_handlers
from core.llm.tools.registry import ToolRegistry

_IMAGE_META: dict[str, tuple[str, str, str, str]] = {
    "scan_text_assets": ("image_agent", "write_pipeline", "image.scan_text_assets", "扫描待生图文字资产"),
    "generate_images": ("image_agent", "write_pipeline", "image.generate_images", "为文字资产生成图片"),
    "search_images": ("image_agent", "write_pipeline", "image.search_images", "搜索并关联配图"),
    "sync_text_from_image": ("image_agent", "write_ad_hoc", "image.sync_text_from_image", "根据实际图片回写文字资产"),
    "list_images": ("image_agent", "read", "image.list_images", "列出已生成图片资产（含链接/本地路径）"),
}


def register_image_tools(registry: ToolRegistry) -> None:
    register_handlers(registry, IMAGE_HANDLERS, _IMAGE_META)
