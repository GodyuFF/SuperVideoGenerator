"""故事书模式：子镜 frame 硬保证、旧数据迁移与可选提示词（style_hints）测试。"""

import pytest

from core.edit.sub_shot_helpers import append_sub_shot_image
from core.guards.script_style import (
    bind_script_style_hints,
    format_style_hints_line,
    normalize_style_hints,
    normalize_style_mode_id,
    parse_target_duration_sec,
)
from core.llm.agent.llm_action import _assert_sub_shots_have_frames
from core.llm.master.pipeline_progress import _frames_cover_all_shots
from core.models.entities import (
    Project,
    Script,
    ShotSubShotImage,
    VideoPlan,
    Shot,
    VideoStyleMode,
)
from core.store.memory import MemoryStore
from tests.support.shot_fixtures import make_shot


def _shot(
    order: int,
    *,
    with_sub_shot: bool = True,
    with_frame: bool = False,
) -> Shot:
    """构造带/不带子镜、带/不带 frame 关联的镜头。"""
    if not with_sub_shot:
        return Shot(order=order, duration_ms=3000, sub_shots=[])
    shot = make_shot(order=order, text=f"镜{order}")
    if with_frame:
        shot.sub_shots[0] = append_sub_shot_image(
            shot.sub_shots[0],
            ShotSubShotImage(frame_asset_id=f"frame_test_{order}"),
        )
    return shot


def test_legacy_dynamic_image_maps_to_storybook():
    """旧持久化数据 dynamic_image 应迁移为 storybook。"""
    assert VideoStyleMode("dynamic_image") is VideoStyleMode.STORYBOOK
    assert normalize_style_mode_id("dynamic_image") == "storybook"
    plan = VideoPlan.model_validate(
        {"script_id": "s1", "mode": "dynamic_image", "shots": []}
    )
    assert plan.mode is VideoStyleMode.STORYBOOK


def test_persist_plan_requires_frames_in_storybook():
    """故事书模式 persist_plan 校验：有子镜但缺 frame 应报错。"""
    shots = [_shot(0, with_frame=True), _shot(1, with_sub_shot=True, with_frame=False)]
    with pytest.raises(ValueError, match="子镜缺少剧本画面 frame"):
        _assert_sub_shots_have_frames(VideoStyleMode.STORYBOOK, shots)


def test_persist_plan_frames_ok_in_storybook():
    """每子镜均有 frame 时校验通过。"""
    shots = [_shot(0, with_frame=True), _shot(1, with_frame=True)]
    _assert_sub_shots_have_frames(VideoStyleMode.STORYBOOK, shots)


def test_persist_plan_no_frame_check_for_ai_video():
    """ai_video 模式不要求 frame。"""
    shots = [_shot(0, with_sub_shot=False)]
    _assert_sub_shots_have_frames(VideoStyleMode.AI_VIDEO, shots)


def test_persist_plan_requires_video_clip_for_ai_video():
    """ai_video 模式 persist 前每子镜须有 video_clip。"""
    from core.llm.agent.llm_action import _assert_sub_shots_have_video_clips
    from core.models.entities import ShotSubShotVideo

    shots = [_shot(0, with_sub_shot=True)]
    with pytest.raises(ValueError, match="video_clip"):
        _assert_sub_shots_have_video_clips(VideoStyleMode.AI_VIDEO, shots)
    sub = shots[0].sub_shots[0]
    sub.videos = [ShotSubShotVideo(video_clip_asset_id="txt_vc_test")]
    _assert_sub_shots_have_video_clips(VideoStyleMode.AI_VIDEO, shots)


def test_frames_cover_all_shots_detects_missing_frame():
    """image_gen 完成判定：故事书模式下缺 frame 的子镜应导致不完成。"""
    store = MemoryStore()
    project = Project(title="故事书")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    plan = VideoPlan(
        script_id=script.id,
        mode=VideoStyleMode.STORYBOOK,
        shots=[_shot(0, with_frame=True), _shot(1, with_sub_shot=True, with_frame=False)],
    )
    store.set_video_plan(plan)
    assert _frames_cover_all_shots(store, script.id) is False

    covered = plan.model_copy(
        update={"shots": [_shot(0, with_frame=True), _shot(1, with_frame=True)]}
    )
    store.set_video_plan(covered)
    assert _frames_cover_all_shots(store, script.id) is True


def test_normalize_style_hints_whitelist():
    """style_hints 仅接受白名单键与非空值。"""
    hints = normalize_style_hints(
        {"image_style": " 水彩插画 ", "target_duration": "60秒", "evil": "x", "empty": ""}
    )
    assert hints == {"image_style": "水彩插画", "target_duration": "60秒"}
    assert normalize_style_hints(None) == {}
    assert normalize_style_hints({"image_style": "  "}) == {}


def test_bind_style_hints_locks_with_style():
    """提示词首次绑定后随风格锁定，不被后续请求覆盖。"""
    script = Script(project_id="p1", title="s1")
    bound = bind_script_style_hints(script, {"image_style": "水彩"})
    assert bound == {"image_style": "水彩"}
    script.style_locked = True
    again = bind_script_style_hints(script, {"image_style": "赛博朋克"})
    assert again == {"image_style": "水彩"}
    assert script.style_hints == {"image_style": "水彩"}


def test_parse_target_duration_sec():
    """预计时长提示词应解析为秒数。"""
    assert parse_target_duration_sec("30秒") == 30
    assert parse_target_duration_sec("60秒") == 60
    assert parse_target_duration_sec("2分钟") == 120
    assert parse_target_duration_sec("3分") == 180
    assert parse_target_duration_sec("90") == 90
    assert parse_target_duration_sec("") is None
    assert parse_target_duration_sec("未知") is None


def test_bind_style_hints_syncs_duration_sec():
    """绑定预计时长提示词时应同步 script.duration_sec。"""
    script = Script(project_id="p1", title="s1", duration_sec=60)
    bind_script_style_hints(script, {"target_duration": "30秒"})
    assert script.duration_sec == 30
    assert script.style_hints == {"target_duration": "30秒"}


def test_format_style_hints_line():
    """未选择时返回空串（不组装提示词），选择后输出中文键值。"""
    assert format_style_hints_line({}) == ""
    assert format_style_hints_line(None) == ""
    line = format_style_hints_line({"image_style": "水彩", "target_duration": "60秒"})
    assert "图片风格=水彩" in line
    assert "预计时长=60秒" in line


def test_project_context_includes_style_hints():
    """子 Agent 项目上下文应包含已锁定的 style_hints；未设置则不出现。"""
    from core.llm.prompt.project_context import (
        build_project_script_context,
        format_project_context_line,
    )

    store = MemoryStore()
    project = Project(title="故事书")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    script.style_hints = {"image_style": "水彩"}
    store.add_script(script)

    ctx = build_project_script_context(
        store, {"project_id": project.id, "script_id": script.id}
    )
    assert "图片风格=水彩" in ctx["style_hints"]
    assert "style_hints" in format_project_context_line(ctx)

    script.style_hints = {}
    ctx2 = build_project_script_context(
        store, {"project_id": project.id, "script_id": script.id}
    )
    assert "style_hints" not in ctx2
