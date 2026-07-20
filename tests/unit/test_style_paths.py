"""视频风格执行路径与图文配置测试。"""

from core.llm.image_text_config import (
    effective_image_source,
    resolve_image_text_config,
    should_prompt_image_source,
)
from core.llm.master import (
    delegates_for_style,
    filter_storyboard_pipeline_actions,
    filter_video_pipeline_actions,
    style_mode_label,
    task_brief_for_step,
    uses_ai_video_pipeline,
    uses_frame_i2v_pipeline,
    uses_image_text_pipeline,
)
from core.llm.agent.prompt_resolver import resolve_agent_prompts
from core.models.entities import (
    ImageSourceMode,
    ImageTextConfig,
    Project,
    ProjectConfig,
    VideoStyleMode,
)


def test_style_mode_labels():
    assert style_mode_label(VideoStyleMode.STORYBOOK) == "故事书模式"
    assert style_mode_label(VideoStyleMode.AI_VIDEO) == "AI 视频模式"
    assert style_mode_label(VideoStyleMode.FRAME_I2V) == "画面图生视频"


def test_legacy_dynamic_comic_migrates_to_storybook_label():
    assert style_mode_label("dynamic_comic") == "故事书模式"


def test_delegates_for_style_storybook():
    actions = delegates_for_style(VideoStyleMode.STORYBOOK)
    assert actions == ["delegate_agent"]


def test_pipeline_ai_video_includes_delegate_agent():
    assert delegates_for_style(VideoStyleMode.AI_VIDEO) == ["delegate_agent"]


def test_task_brief_differs_by_style():
    image_brief = task_brief_for_step("image_gen", VideoStyleMode.STORYBOOK)
    ai_brief = task_brief_for_step("video_gen", VideoStyleMode.AI_VIDEO)
    assert "故事书" in image_brief
    assert "AI 视频" in ai_brief


def test_uses_image_text_pipeline():
    assert uses_image_text_pipeline(VideoStyleMode.STORYBOOK)
    assert uses_image_text_pipeline(VideoStyleMode.FRAME_I2V)
    assert uses_image_text_pipeline("dynamic_comic")
    assert not uses_image_text_pipeline(VideoStyleMode.AI_VIDEO)


def test_uses_ai_video_pipeline():
    assert uses_ai_video_pipeline(VideoStyleMode.AI_VIDEO)
    assert uses_ai_video_pipeline(VideoStyleMode.FRAME_I2V)
    assert not uses_ai_video_pipeline(VideoStyleMode.STORYBOOK)


def test_uses_frame_i2v_pipeline():
    assert uses_frame_i2v_pipeline(VideoStyleMode.FRAME_I2V)
    assert not uses_frame_i2v_pipeline(VideoStyleMode.STORYBOOK)
    assert not uses_frame_i2v_pipeline(VideoStyleMode.AI_VIDEO)


def test_filter_storyboard_pipeline_by_style():
    full = [
        "load_context",
        "create_shots",
        "create_frames",
        "create_video_clips",
        "persist_plan",
    ]
    storybook = filter_storyboard_pipeline_actions(full, VideoStyleMode.STORYBOOK)
    assert "create_frames" in storybook
    assert "create_video_clips" not in storybook
    ai = filter_storyboard_pipeline_actions(full, VideoStyleMode.AI_VIDEO)
    assert "create_video_clips" in ai
    assert "create_frames" not in ai
    frame_i2v = filter_storyboard_pipeline_actions(full, VideoStyleMode.FRAME_I2V)
    assert "create_frames" in frame_i2v
    assert "create_video_clips" in frame_i2v


def test_filter_video_pipeline_excludes_legacy():
    raw = [
        "load_shots",
        "scan_video_clips",
        "generate_clips",
        "generate_video_clips",
        "generate_from_timeline",
    ]
    filtered = filter_video_pipeline_actions(raw)
    assert filtered == ["generate_video_clips", "generate_from_timeline"]


def test_storybook_prompt_profile():
    bundle = resolve_agent_prompts(
        "image_agent",
        style_mode=VideoStyleMode.STORYBOOK,
    )
    assert "故事书" in bundle.role_prompt or "配图" in bundle.role_prompt


def test_image_source_user_choice_prompt():
    cfg = ImageTextConfig(source_mode=ImageSourceMode.USER_CHOICE)
    assert should_prompt_image_source(cfg, VideoStyleMode.STORYBOOK)
    assert not should_prompt_image_source(cfg, VideoStyleMode.AI_VIDEO)


def test_effective_image_source_from_popup():
    cfg = ImageTextConfig(source_mode=ImageSourceMode.USER_CHOICE)
    assert effective_image_source(cfg, "search") == ImageSourceMode.SEARCH
    assert effective_image_source(cfg, None) == ImageSourceMode.GENERATE


def test_resolve_image_text_config_project_override():
    project = Project(
        title="t",
        config=ProjectConfig(
            image_text=ImageTextConfig(source_mode=ImageSourceMode.SEARCH)
        ),
    )
    resolved = resolve_image_text_config(project, None)
    assert resolved.source_mode == ImageSourceMode.SEARCH
