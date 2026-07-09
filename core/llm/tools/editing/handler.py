"""editing_agent tools handlers."""

from core.llm.tools.editing.timeline_handler import (
    handle_analyze_edit_timeline,
    handle_get_edit_timeline,
    handle_load_edit_context,
    handle_plan_edit_timeline,
    handle_report_missing_assets,
    handle_validate_edit_assets,
)
from core.llm.tools.shared.media_common import make_write_handler, read_media_list
from core.models.entities import MediaAssetType

handle_gather_media = make_write_handler("editing_agent", "gather_media")
handle_compose_final = make_write_handler("editing_agent", "compose_final")
handle_list_final = lambda store, ctx, args: read_media_list(
    store, ctx, args, media_type=MediaAssetType.FINAL
)

HANDLERS = {
    "load_edit_context": handle_load_edit_context,
    "plan_edit_timeline": handle_plan_edit_timeline,
    "validate_edit_assets": handle_validate_edit_assets,
    "report_missing_assets": handle_report_missing_assets,
    "get_edit_timeline": handle_get_edit_timeline,
    "analyze_edit_timeline": handle_analyze_edit_timeline,
    "gather_media": handle_gather_media,
    "compose_final": handle_compose_final,
    "list_final": handle_list_final,
}
