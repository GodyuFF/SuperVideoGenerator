"""video_clip 看板条目：preview 为文案，preview_url / media 为可播放链路（不重复）。"""

from core.board.builder import _video_clip_item
from core.models.entities import MediaAsset, MediaAssetType, Project, Script, TextAsset, TextAssetType
from core.store.memory import MemoryStore


def test_video_clip_board_item_keeps_preview_text_separate_from_media():
    """已生成视频时 preview 仍为摘要，preview_url 与 media[].url 同源且各一条。"""
    store = MemoryStore()
    project = Project(title="视频预览测试")
    store.add_project(project)
    script = Script(project_id=project.id, title="第一集", content_md="# 开场")
    store.add_script(script)
    clip = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.VIDEO_CLIP,
        name="春日推轨",
        content={
            "summary": "金色花田推轨摘要",
            "video_prompt": "slow dolly through a golden flower field at sunrise",
        },
        source_script_id=script.id,
    )
    store.add_text_asset(clip)
    media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.VIDEO,
        name="clip.mp4",
        url="projects/proj_x/scripts/scr_x/assets/media/clip.mp4",
        source_asset_id=clip.id,
    )
    stored = store.add_media_asset(media)
    store.text_assets[clip.id] = clip.model_copy(update={"primary_media_id": stored.id})

    item = _video_clip_item(store, store.text_assets[clip.id], script_id=script.id)
    preview_text = str(item.get("preview") or "")
    assert "金色花田" in preview_text
    assert "clip.mp4" not in preview_text

    preview_url = str(item.get("preview_url") or "")
    assert "clip.mp4" in preview_url
    videos = item.get("videos") or []
    media_list = item.get("media") or []
    assert len(videos) == 1
    assert len([m for m in media_list if m.get("type") == "video"]) == 1
    assert preview_url == str(videos[0].get("url") or "")
