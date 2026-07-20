"""视频 generate_clips 收集逻辑单元测试。"""

from __future__ import annotations

from core.llm.tools.video.generate import collect_shot_video_specs
from core.models.entities import (
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    ShotSubShotImage,
    TextAsset,
    TextAssetType,
    VideoPlan,
    VideoStyleMode,
)
from core.store.memory import MemoryStore
from tests.support.shot_fixtures import make_shot


def _store_with_ai_video_shot() -> tuple[MemoryStore, str]:
    """构建 AI 视频风格剧本与含画面镜头的 store。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(
        project_id=project.id,
        title="s",
        style_mode=VideoStyleMode.AI_VIDEO.value,
    )
    store.add_script(script)
    frame = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.FRAME,
        name="画面1",
        content={"description": "夕阳海滩", "element_refs": {}},
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

    shot = make_shot(order=0, text="镜一")
    sub = shot.sub_shots[0]
    shot = shot.model_copy(
        update={
            "sub_shots": [
                sub.model_copy(
                    update={
                        "images": [
                            ShotSubShotImage(
                                frame_asset_id=frame.id,
                                media_id=media.id,
                                kind="video",
                            )
                        ],
                    }
                )
            ],
        }
    )
    store.set_video_plan(
        VideoPlan(script_id=script.id, mode=VideoStyleMode.AI_VIDEO, shots=[shot])
    )
    return store, script.id


def test_collect_shot_video_specs_resolves_style_modes() -> None:
    """collect_shot_video_specs 应解析剧本风格 video 子模式，避免 NameError 回归。"""
    store, script_id = _store_with_ai_video_shot()
    specs = collect_shot_video_specs(store, script_id, {})
    assert len(specs) == 1
    assert specs[0].mode == "img2video"
    assert specs[0].image_url
