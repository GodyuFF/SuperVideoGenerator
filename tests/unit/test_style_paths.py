"""视频风格执行路径与图文配置测试。"""

from core.llm.image_text_config import (
    effective_image_source,
    resolve_image_text_config,
    should_prompt_image_source,
)
from core.llm.master import (
    pipeline_for_style,
    style_mode_label,
    task_brief_for_step,
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
    assert style_mode_label(VideoStyleMode.DYNAMIC_IMAGE) == "动态图文模式"
    assert style_mode_label(VideoStyleMode.DYNAMIC_COMIC) == "动态漫画模式"
    assert style_mode_label(VideoStyleMode.AI_VIDEO) == "AI 视频模式"


def test_pipeline_dynamic_image_and_comic_skip_video_gen():
    for mode in (VideoStyleMode.DYNAMIC_IMAGE, VideoStyleMode.DYNAMIC_COMIC):
        pipeline = pipeline_for_style(mode)
        assert "delegate_script_design" in pipeline
        assert "delegate_image_gen" in pipeline
        assert "delegate_video_gen" not in pipeline
        assert pipeline[-2:] == ["delegate_tts_gen", "delegate_edit_compose"]


def test_pipeline_ai_video_includes_video_gen():
    pipeline = pipeline_for_style(VideoStyleMode.AI_VIDEO)
    assert "delegate_video_gen" in pipeline


def test_task_brief_differs_by_style():
    image_brief = task_brief_for_step("image_gen", VideoStyleMode.DYNAMIC_IMAGE)
    comic_brief = task_brief_for_step("image_gen", VideoStyleMode.DYNAMIC_COMIC)
    assert "动态图文" in image_brief
    assert "动态漫画" in comic_brief
    assert image_brief != comic_brief


def test_uses_image_text_pipeline():
    assert uses_image_text_pipeline(VideoStyleMode.DYNAMIC_IMAGE)
    assert uses_image_text_pipeline(VideoStyleMode.DYNAMIC_COMIC)
    assert not uses_image_text_pipeline(VideoStyleMode.AI_VIDEO)


def test_dynamic_comic_prompt_profile():
    bundle = resolve_agent_prompts(
        "image_agent",
        style_mode=VideoStyleMode.DYNAMIC_COMIC,
    )
    assert "动态漫画" in bundle.role_prompt


def test_image_source_user_choice_prompt():
    cfg = ImageTextConfig(source_mode=ImageSourceMode.USER_CHOICE)
    assert should_prompt_image_source(cfg, VideoStyleMode.DYNAMIC_IMAGE)
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
