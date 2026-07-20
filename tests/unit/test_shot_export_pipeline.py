"""镜内多轨 Shot → 投影 → 导出全链路验证。"""

from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from core.edit.asset_resolver import validate_edit_timeline
from core.edit.compose import compose_timeline_plan, gather_timeline_media
from core.edit.export_settings import ExportConfigManager
from core.edit.ffmpeg_renderer import export_timeline_to_mp4
from core.edit.nle_export import export_timeline_to_premiere_package
from core.edit.shot_flatten import apply_timeline_edits_to_shots
from core.edit.timeline import compile_timeline_from_shots
from core.models.entities import VideoStyleMode
from tests.unit.test_ffmpeg_renderer import _fake_composite_slice


@pytest.fixture
def enabled_export_manager() -> ExportConfigManager:
    """单元测试用：显式启用 FFmpeg 导出管理器。"""
    mgr = ExportConfigManager()
    mgr.update(enabled=True)
    return mgr


def test_shot_multitrack_timeline_compose_and_validate(timeline_store) -> None:
    """镜内多轨投影的时间轴应通过 compose 与 validate。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    assert plan
    timeline = timeline_store.get_edit_timeline_for_script(script_id)
    assert timeline

    compose = compose_timeline_plan(
        timeline_store, timeline, style_mode=VideoStyleMode.STORYBOOK
    )
    assert compose["segments"]
    assert compose["duration_ms"] > 0

    media = gather_timeline_media(timeline_store, timeline)
    assert not media.get("missing_refs")

    validation = validate_edit_timeline(timeline_store, timeline)
    assert validation.ready


def test_shot_multitrack_ffmpeg_export_mock(
    timeline_store, enabled_export_manager, tmp_path
) -> None:
    """镜内多轨投影时间轴应可走 FFmpeg 导出路径（mock subprocess）。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    project_id = timeline_store._test_project_id  # type: ignore[attr-defined]
    timeline = timeline_store.get_edit_timeline_for_script(script_id)
    assert timeline
    out = tmp_path / "shot_pipeline_out.mp4"

    with patch("core.edit.ffmpeg_renderer._run_ffmpeg"), patch(
        "core.edit.ffmpeg_renderer.is_ffmpeg_available", return_value=True
    ), patch("core.edit.ffmpeg_renderer.shutil.rmtree"), patch(
        "core.edit.ffmpeg_renderer._render_composite_slice", side_effect=_fake_composite_slice
    ), patch(
        "core.edit.ffmpeg_renderer._mux_av"
    ) as mux:
        mux.side_effect = lambda *a, **k: out.write_bytes(b"fake")
        result = export_timeline_to_mp4(
            timeline_store,
            timeline,
            out,
            project_id=project_id,
            script_id=script_id,
            style_mode=VideoStyleMode.STORYBOOK,
            manager=enabled_export_manager,
        )
        assert result.segment_count >= 1


def test_shot_multitrack_nle_export(timeline_store, tmp_path) -> None:
    """镜内多轨投影时间轴应可导出 Premiere 工程包。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    project_id = timeline_store._test_project_id  # type: ignore[attr-defined]
    timeline = timeline_store.get_edit_timeline_for_script(script_id)
    assert timeline

    out = tmp_path / "shot_pipeline_nle.zip"
    result = export_timeline_to_premiere_package(
        timeline_store,
        timeline,
        out,
        project_id=project_id,
        script_id=script_id,
        sequence_name="镜内多轨测试",
    )
    assert out.is_file()
    assert result.clip_count >= 1
    with zipfile.ZipFile(out, "r") as zf:
        assert "project.xml" in zf.namelist()


def test_opencut_roundtrip_then_compose(timeline_store) -> None:
    """OpenCut 手改回写 Shot 后重新投影，compose 仍应有效。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    assert plan
    timeline = timeline_store.get_edit_timeline_for_script(script_id)
    assert timeline

    clip = timeline.video_layers[0].clips[0]
    edited = clip.model_copy(update={"end_ms": int(clip.end_ms or 0) + 400})
    timeline = timeline.model_copy(
        update={
            "video_layers": [
                timeline.video_layers[0].model_copy(
                    update={"clips": [edited, *timeline.video_layers[0].clips[1:]]}
                ),
                *timeline.video_layers[1:],
            ],
            "user_edited": True,
        }
    )

    restored_shots = apply_timeline_edits_to_shots(list(plan.shots), timeline)
    assert restored_shots[0].duration_ms >= int(plan.shots[0].duration_ms or 0)

    recompiled = compile_timeline_from_shots(
        timeline_store,
        script_id=script_id,
        plan=plan.model_copy(update={"shots": restored_shots}),
    )
    compose = compose_timeline_plan(
        timeline_store, recompiled, style_mode=VideoStyleMode.STORYBOOK
    )
    assert compose["segments"]
    assert validate_edit_timeline(timeline_store, recompiled).ready
