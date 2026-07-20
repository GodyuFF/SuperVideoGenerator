"""图文看板条目须提供 preview_url（媒体链路），preview 保持摘要文案。"""

from core.board.builder import _image_text_item
from core.models.entities import MediaAsset, MediaAssetType, Project, Script, TextAsset, TextAssetType
from core.store.memory import MemoryStore


def test_frame_board_item_exposes_preview_url_separate_from_text_preview():
    """frame 条目：preview 为文案，preview_url / images[].url 为可加载媒体。"""
    store = MemoryStore()
    project = Project(title="预览测试")
    store.add_project(project)
    script = Script(project_id=project.id, title="第一集", content_md="# 开场")
    store.add_script(script)
    frame = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.FRAME,
        name="春日花田",
        content={
            "summary": "金色花田摘要文案",
            "image_prompt": "a golden flower field under soft sunrise light, wide establishing shot",
        },
        source_script_id=script.id,
    )
    store.add_text_asset(frame)
    media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="frame.png",
        url="projects/proj_x/scripts/scr_x/assets/media/frame.png",
        source_asset_id=frame.id,
    )
    stored = store.add_media_asset(media)
    store.text_assets[frame.id] = frame.model_copy(
        update={"primary_media_id": stored.id}
    )

    item = _image_text_item(store, store.text_assets[frame.id], script_id=script.id)
    preview_text = str(item.get("preview") or "")
    assert "金色花田" in preview_text or "摘要" in preview_text
    preview_url = str(item.get("preview_url") or "")
    assert "frame.png" in preview_url
    assert item["images"]
    assert "frame.png" in str(item["images"][0].get("url") or "")
