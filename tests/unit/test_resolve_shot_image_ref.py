"""resolve_shot_image_ref 仅返回画面 IMAGE，禁止视频与 character 回退。"""

from core.edit.timeline import resolve_shot_image_ref, resolve_shot_video_ref
from core.models.entities import (
    AssetScope,
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    ShotSubShotImage,
    ShotSubShotVideo,
    TextAsset,
    TextAssetType,
    Shot,
)
from core.store.memory import MemoryStore
from tests.support.frame_fixtures import ensure_shot_frame_image
from tests.support.image_text_fixtures import character_content
from tests.support.shot_fixtures import make_shot


def test_resolve_prefers_frame_over_character():
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)

    char = TextAsset(
        project_id=project.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.PROJECT_SHARED,
        name="角色",
        content=character_content(),
        source_script_id=script.id,
    )
    store.add_text_asset(char)
    char_media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="char_green",
        url="https://images.test/char.png",
        source_asset_id=char.id,
    )
    store.add_media_asset(char_media)
    char.primary_media_id = char_media.id
    store.update_text_asset(char)

    shot = make_shot(order=0, text="镜头")
    shot.sub_shots[0].element_refs = {"character": [char.id]}
    frame, frame_media = ensure_shot_frame_image(
        store,
        project_id=project.id,
        script_id=script.id,
        shot=shot,
        element_refs={"character": [char.id], "frame": []},
        image_url="https://images.test/frame.png",
    )
    assert resolve_shot_image_ref(store, shot) == frame_media.id


def test_resolve_does_not_fallback_to_character():
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)

    char = TextAsset(
        project_id=project.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.PROJECT_SHARED,
        name="角色",
        content=character_content(),
        source_script_id=script.id,
    )
    store.add_text_asset(char)
    char_media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="char",
        url="https://images.test/char.png",
        source_asset_id=char.id,
    )
    store.add_media_asset(char_media)
    char.primary_media_id = char_media.id
    store.update_text_asset(char)

    shot = make_shot(order=0, text="镜头")
    shot.sub_shots[0].element_refs = {"character": [char.id]}
    assert resolve_shot_image_ref(store, shot) is None


def test_resolve_image_ignores_video_media_in_images_slot():
    """误绑到 images[] 的视频 media 不得作为画面预览。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)

    video = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.VIDEO,
        name="clip",
        url="https://videos.test/clip.mp4",
    )
    store.add_media_asset(video)

    shot = make_shot(order=0, text="镜头")
    shot.sub_shots[0] = shot.sub_shots[0].model_copy(
        update={
            "images": [
                ShotSubShotImage(kind="video", media_id=video.id, frame_asset_id=""),
            ],
            "videos": [
                ShotSubShotVideo(media_id=video.id, source_kind="video"),
            ],
        }
    )
    if shot.video_tracks and shot.video_tracks[0].clips:
        clip = shot.video_tracks[0].clips[0].model_copy(
            update={"media_id": video.id, "source_kind": "video"}
        )
        shot.video_tracks[0] = shot.video_tracks[0].model_copy(update={"clips": [clip]})

    assert resolve_shot_image_ref(store, shot) is None
    assert resolve_shot_video_ref(store, shot) == video.id
