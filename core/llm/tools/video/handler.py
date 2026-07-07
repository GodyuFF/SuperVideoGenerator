"""video_agent tools handlers."""

from core.llm.tools.shared.media_common import make_write_handler, read_media_list
from core.models.entities import MediaAssetType

handle_load_shots = make_write_handler("video_agent", "load_shots")
handle_generate_clips = make_write_handler("video_agent", "generate_clips")
handle_generate_from_timeline = make_write_handler("video_agent", "generate_from_timeline")
handle_list_videos = lambda store, ctx, args: read_media_list(
    store, ctx, args, media_type=MediaAssetType.VIDEO
)

HANDLERS = {
    "load_shots": handle_load_shots,
    "generate_clips": handle_generate_clips,
    "generate_from_timeline": handle_generate_from_timeline,
    "list_videos": handle_list_videos,
}
