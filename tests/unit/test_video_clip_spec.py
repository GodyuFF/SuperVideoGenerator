"""video_clip 视频生成规格解析单元测试。"""

from __future__ import annotations

from core.llm.tools.video.shot_spec import resolve_video_clip_gen_spec
from core.models.entities import (
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    TextAsset,
    TextAssetType,
)
from core.store.memory import MemoryStore


def _store_with_video_clip() -> tuple[MemoryStore, str, str]:
    """构建含 video_clip 与参考图的 store。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    frame = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.FRAME,
        name="画面1",
        content={"description": "海滩", "element_refs": {}},
    )
    store.add_text_asset(frame)
    media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="frame.png",
        url="https://example.test/frame.png",
    )
    store.add_media_asset(media)
    frame.primary_media_id = media.id
    store.update_text_asset(frame)

    clip = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.VIDEO_CLIP,
        name="片段1",
        content={
            "summary": "海浪轻拍",
            "video_prompt": "海浪轻轻拍打沙滩，电影感",
            "tags": ["ocean", "calm"],
            "element_refs": {"frame": [frame.id]},
            "video_mode": "auto",
        },
    )
    store.add_text_asset(clip)
    return store, script.id, clip.id


def test_resolve_video_clip_img2video() -> None:
    """有 frame 参考图时应解析为图生视频。"""
    store, _, clip_id = _store_with_video_clip()
    spec = resolve_video_clip_gen_spec(
        store,
        clip_id,
        allowed_modes=["text2video", "img2video", "keyframes"],
    )
    assert spec.mode == "img2video"
    assert spec.video_clip_asset_id == clip_id
    assert spec.image_url


def test_resolve_video_clip_text2video() -> None:
    """无参考图时应为文生视频。"""
    store, _, clip_id = _store_with_video_clip()
    clip = store.get_text_asset(clip_id)
    assert clip
    clip.content = {
        "summary": "抽象光斑",
        "video_prompt": "抽象光斑流动",
        "element_refs": {},
        "media_refs": [],
    }
    store.update_text_asset(clip)
    spec = resolve_video_clip_gen_spec(
        store,
        clip_id,
        allowed_modes=["text2video", "img2video", "keyframes"],
    )
    assert spec.mode == "text2video"
    assert spec.image_url is None
