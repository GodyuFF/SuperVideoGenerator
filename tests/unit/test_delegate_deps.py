"""主编排 delegate 依赖与动态选步测试。"""

from core.llm.master.delegate_deps import (
    delegates_for_style,
    eligible_delegates,
    is_hard_blocked,
    resolve_delegate_readiness,
)
from core.llm.master.delegate_tool import DELEGATE_AGENT_ACTION
from core.models.entities import (
    Project,
    Script,
    TextAsset,
    TextAssetType,
    VideoPlan,
    Shot,
    VideoStyleMode,
)
from core.store.memory import MemoryStore
from tests.support.frame_fixtures import ensure_shot_frame_image


def test_delegates_for_style_storybook_excludes_video_gen():
    actions = delegates_for_style(VideoStyleMode.STORYBOOK)
    assert actions == [DELEGATE_AGENT_ACTION]


def test_delegates_for_style_ai_video_includes_delegate_agent():
    actions = delegates_for_style(VideoStyleMode.AI_VIDEO)
    assert actions == [DELEGATE_AGENT_ACTION]


def test_tts_hard_soft_blockers_without_plan():
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1", duration_sec=30)
    store.add_script(script)

    rows = {r["step_type"]: r for r in resolve_delegate_readiness(store, script.id, VideoStyleMode.STORYBOOK)}
    assert rows["tts_gen"]["soft_blockers"]
    assert not rows["script_design"]["hard_blockers"]


def test_image_gen_eligible_after_script():
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1", duration_sec=30, content_md="# 测试")
    store.add_script(script)

    eligible = eligible_delegates(store, script.id, VideoStyleMode.STORYBOOK)
    assert eligible == [DELEGATE_AGENT_ACTION]


def test_video_gen_hard_blocked_on_storybook():
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1", duration_sec=30)
    store.add_script(script)
    from tests.support.shot_fixtures import make_shot

    shot = make_shot(order=0, duration_ms=3000, text="旁白")
    ensure_shot_frame_image(
        store,
        project_id=project.id,
        script_id=script.id,
        shot=shot,
        image_url="https://images.test/f.png",
    )
    store.set_video_plan(
        VideoPlan(script_id=script.id, mode=VideoStyleMode.STORYBOOK, shots=[shot])
    )
    reason = is_hard_blocked(
        store, script.id, VideoStyleMode.STORYBOOK, "video_agent"
    )
    assert reason is not None


def test_shot_detail_soft_blocks_without_video_on_ai_video():
    """AI 视频模式下未完成 video_gen 时，分镜复核应有 soft_blocker。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1", duration_sec=30, content_md="# 测")
    store.add_script(script)
    from tests.support.shot_fixtures import make_shot

    shot = make_shot(order=0, duration_ms=3000, text="旁白")
    ensure_shot_frame_image(
        store,
        project_id=project.id,
        script_id=script.id,
        shot=shot,
        image_url="https://images.test/f.png",
    )
    store.set_video_plan(
        VideoPlan(script_id=script.id, mode=VideoStyleMode.AI_VIDEO, shots=[shot])
    )
    rows = {
        r["step_type"]: r
        for r in resolve_delegate_readiness(store, script.id, VideoStyleMode.AI_VIDEO)
    }
    blockers = rows["shot_detail"]["soft_blockers"]
    assert any("video_gen" in b or "video" in b for b in blockers)


def test_frame_i2v_video_gen_soft_blocks_without_image_gen():
    """frame_i2v 在配图未完成时，video_agent 应有 soft_blocker。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(
        project_id=project.id,
        title="s1",
        duration_sec=30,
        content_md="# 测",
        style_mode=VideoStyleMode.FRAME_I2V,
    )
    store.add_script(script)
    from tests.support.shot_fixtures import make_shot
    from core.models.entities import ShotSubShotImage, ShotSubShotVideo

    shot = make_shot(order=0, duration_ms=3000, text="旁白")
    frame = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.FRAME,
        name="画面",
        content={"image_prompt": "a cat"},
    )
    store.add_text_asset(frame)
    clip = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.VIDEO_CLIP,
        name="片段",
        content={"video_prompt": "slow pan"},
    )
    store.add_text_asset(clip)
    shot.sub_shots[0].images = [
        ShotSubShotImage(kind="static", frame_asset_id=frame.id, media_id="")
    ]
    shot.sub_shots[0].videos = [
        ShotSubShotVideo(video_clip_asset_id=clip.id, media_id="")
    ]
    store.set_video_plan(
        VideoPlan(script_id=script.id, mode=VideoStyleMode.FRAME_I2V, shots=[shot])
    )
    rows = {
        r["step_type"]: r
        for r in resolve_delegate_readiness(store, script.id, VideoStyleMode.FRAME_I2V)
    }
    blockers = rows["video_gen"]["soft_blockers"]
    assert any("image_gen" in b for b in blockers)
    assert rows["video_gen"]["ready"] is False
