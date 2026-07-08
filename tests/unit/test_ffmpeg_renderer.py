"""ffmpeg_renderer 单元测试（mock subprocess）。"""

from pathlib import Path
from unittest.mock import patch

import pytest

from core.edit.compose import compose_timeline_plan
from core.edit.ffmpeg_renderer import FfmpegExportError, export_timeline_to_mp4
from core.edit.timeline import compile_timeline_from_shots
from core.models.entities import VideoStyleMode
from tests.unit.test_edit_timeline_validation import store_with_plan
from tests.support.timeline_store_fixture import timeline_store


def test_export_timeline_to_mp4_mock_ffmpeg(timeline_store):
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    project_id = timeline_store._test_project_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    assert plan
    timeline = compile_timeline_from_shots(
        timeline_store,
        script_id=script_id,
        plan=plan,
        tts_by_shot={plan.shots[0].id: timeline_store._test_audio_id},  # type: ignore[attr-defined]
    )
    timeline_store.set_edit_timeline(timeline)
    out = Path("fake_out.mp4")

    def fake_render(**kwargs):
        output_path = kwargs["output_path"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"seg")

    with patch("core.edit.ffmpeg_renderer._run_ffmpeg"), patch(
        "core.edit.ffmpeg_renderer.is_ffmpeg_available", return_value=True
    ), patch("core.edit.ffmpeg_renderer.shutil.rmtree"), patch(
        "core.edit.ffmpeg_renderer._render_image_segment", side_effect=fake_render
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
            style_mode=VideoStyleMode.DYNAMIC_IMAGE,
        )
        assert result.segment_count >= 1


def test_export_timeline_muxes_audio_when_video_only_timeline(timeline_store):
    """仅 video 轨、Store 有 TTS 时，导出前应 enrich audio 并传入 _mux_av。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    project_id = timeline_store._test_project_id  # type: ignore[attr-defined]
    audio_id = timeline_store._test_audio_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    assert plan
    shot_id = plan.shots[0].id

    audio = timeline_store.media_assets[audio_id]
    audio.metadata = {**(audio.metadata or {}), "shot_id": shot_id}

    timeline = timeline_store.get_edit_timeline_for_script(script_id)
    assert timeline
    timeline = timeline.model_copy(
        update={
            "tracks": {
                **timeline.tracks,
                "audio": [],
                "subtitle": [],
            }
        }
    )
    out = Path("fake_audio_mux.mp4")

    def fake_render(**kwargs):
        output_path = kwargs["output_path"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"seg")

    with patch("core.edit.ffmpeg_renderer._run_ffmpeg"), patch(
        "core.edit.ffmpeg_renderer.is_ffmpeg_available", return_value=True
    ), patch("core.edit.ffmpeg_renderer.shutil.rmtree"), patch(
        "core.edit.ffmpeg_renderer._render_image_segment", side_effect=fake_render
    ), patch(
        "core.edit.ffmpeg_renderer._resolve_media_path",
        return_value=Path("fake_audio.mp3"),
    ), patch(
        "core.edit.ffmpeg_renderer._mix_audio_tracks",
        return_value=None,
    ), patch(
        "core.edit.ffmpeg_renderer._mux_av"
    ) as mux:
        mux.side_effect = lambda *a, **k: out.write_bytes(b"fake")
        export_timeline_to_mp4(
            timeline_store,
            timeline,
            out,
            project_id=project_id,
            script_id=script_id,
            style_mode=VideoStyleMode.DYNAMIC_IMAGE,
        )
        assert mux.called
        audio_path = mux.call_args[0][2]
        assert audio_path is not None


def test_transform_needs_overlay_detects_scaled_transform():
    from core.edit.ffmpeg_renderer import _transform_needs_overlay

    assert _transform_needs_overlay({"width": 0.5, "height": 0.5}) is True
    assert _transform_needs_overlay({"x": 0.5, "y": 0.5, "width": 1, "height": 1}) is False


def test_export_timeline_burns_subtitles(timeline_store):
    """含 subtitle 轨时导出应调用 burn_subtitles。"""
    import shutil

    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    project_id = timeline_store._test_project_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    assert plan
    timeline = compile_timeline_from_shots(
        timeline_store,
        script_id=script_id,
        plan=plan,
        tts_by_shot={plan.shots[0].id: timeline_store._test_audio_id},  # type: ignore[attr-defined]
    )
    assert timeline.tracks.get("subtitle")
    out = Path("fake_subs.mp4")

    def fake_composite(**kwargs):
        output_path = kwargs["temp_dir"] / f"slice_{kwargs['idx']:03d}.mp4"
        output_path.write_bytes(b"slice")
        return output_path

    def fake_burn(_ffmpeg, video_in, _ass_path, video_out, _settings, *, run_ffmpeg, **kwargs):
        video_out.parent.mkdir(parents=True, exist_ok=True)
        if video_in.is_file():
            shutil.copy(video_in, video_out)
        else:
            video_out.write_bytes(b"subs")

    with patch("core.edit.ffmpeg_renderer._run_ffmpeg"), patch(
        "core.edit.ffmpeg_renderer.is_ffmpeg_available", return_value=True
    ), patch("core.edit.ffmpeg_renderer.shutil.rmtree"), patch(
        "core.edit.ffmpeg_renderer._render_composite_slice", side_effect=fake_composite
    ), patch(
        "core.edit.ffmpeg_renderer._resolve_media_path",
        return_value=Path("fake_audio.mp3"),
    ), patch(
        "core.edit.ffmpeg_renderer._mix_audio_tracks",
        return_value=None,
    ), patch(
        "core.edit.ffmpeg_renderer.burn_subtitles", side_effect=fake_burn
    ) as burn, patch(
        "core.edit.ffmpeg_renderer._mux_av"
    ) as mux:
        mux.side_effect = lambda *a, **k: out.write_bytes(b"fake")
        export_timeline_to_mp4(
            timeline_store,
            timeline,
            out,
            project_id=project_id,
            script_id=script_id,
            style_mode=VideoStyleMode.DYNAMIC_IMAGE,
        )
        burn.assert_called_once()


def test_export_timeline_skip_subtitles(timeline_store):
    """skip_subtitles=True 时不回填字幕轨、不调用 burn_subtitles。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    project_id = timeline_store._test_project_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    assert plan
    timeline = compile_timeline_from_shots(
        timeline_store,
        script_id=script_id,
        plan=plan,
        tts_by_shot={plan.shots[0].id: timeline_store._test_audio_id},  # type: ignore[attr-defined]
    )
    timeline = timeline.model_copy(
        update={"tracks": {**timeline.tracks, "subtitle": []}}
    )
    out = Path("fake_skip_subs.mp4")

    def fake_render(**kwargs):
        output_path = kwargs["output_path"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"seg")

    with patch("core.edit.ffmpeg_renderer._run_ffmpeg"), patch(
        "core.edit.ffmpeg_renderer.is_ffmpeg_available", return_value=True
    ), patch("core.edit.ffmpeg_renderer.shutil.rmtree"), patch(
        "core.edit.ffmpeg_renderer._render_image_segment", side_effect=fake_render
    ), patch(
        "core.edit.ffmpeg_renderer.burn_subtitles"
    ) as burn, patch(
        "core.edit.ffmpeg_renderer._mux_av"
    ) as mux:
        mux.side_effect = lambda *a, **k: out.write_bytes(b"fake")
        export_timeline_to_mp4(
            timeline_store,
            timeline,
            out,
            project_id=project_id,
            script_id=script_id,
            style_mode=VideoStyleMode.DYNAMIC_IMAGE,
            skip_subtitles=True,
        )
        burn.assert_not_called()


def test_compose_timeline_plan_multi_layer_slices(timeline_store):
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    assert plan
    timeline = compile_timeline_from_shots(
        timeline_store,
        script_id=script_id,
        plan=plan,
    )
    main_layer = timeline.video_layers[0]
    pip_layer_id = "vly_pip"
    pip_clip = main_layer.clips[0].model_copy(
        update={
            "id": "clip_pip",
            "layer_id": pip_layer_id,
            "start_ms": 500,
            "end_ms": 3500,
            "transform": main_layer.clips[0].transform.model_copy(
                update={"x": 0.8, "y": 0.2, "width": 0.25, "height": 0.25}
            )
            if main_layer.clips[0].transform
            else None,
        }
    )
    from core.models.entities import EditVideoLayer

    timeline = timeline.model_copy(
        update={
            "video_layers": [
                main_layer,
                EditVideoLayer(
                    id=pip_layer_id,
                    name="画中画",
                    z_index=1,
                    clips=[pip_clip],
                ),
            ]
        }
    )
    plan_data = compose_timeline_plan(
        timeline_store, timeline, style_mode=VideoStyleMode.DYNAMIC_IMAGE
    )
    slices = plan_data.get("composite_slices") or []
    assert slices
    multi = [s for s in slices if len(s.get("layers", [])) > 1]
    assert multi


def test_export_timeline_multilayer_uses_composite_slice(timeline_store):
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    project_id = timeline_store._test_project_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    assert plan
    timeline = compile_timeline_from_shots(
        timeline_store,
        script_id=script_id,
        plan=plan,
        tts_by_shot={plan.shots[0].id: timeline_store._test_audio_id},  # type: ignore[attr-defined]
    )
    main_layer = timeline.video_layers[0]
    pip_layer_id = "vly_pip"
    pip_clip = main_layer.clips[0].model_copy(
        update={
            "id": "clip_pip",
            "layer_id": pip_layer_id,
            "start_ms": 500,
            "end_ms": 3500,
        }
    )
    from core.models.entities import EditVideoLayer

    timeline = timeline.model_copy(
        update={
            "video_layers": [
                main_layer,
                EditVideoLayer(
                    id=pip_layer_id,
                    name="画中画",
                    z_index=1,
                    clips=[pip_clip],
                ),
            ]
        }
    )
    timeline_store.set_edit_timeline(timeline)
    out = Path("fake_multilayer.mp4")

    def fake_composite(**kwargs):
        output_path = kwargs["temp_dir"] / f"slice_{kwargs['idx']:03d}.mp4"
        output_path.write_bytes(b"slice")
        return output_path

    with patch("core.edit.ffmpeg_renderer._run_ffmpeg"), patch(
        "core.edit.ffmpeg_renderer.is_ffmpeg_available", return_value=True
    ), patch("core.edit.ffmpeg_renderer.shutil.rmtree"), patch(
        "core.edit.ffmpeg_renderer._render_composite_slice", side_effect=fake_composite
    ) as composite, patch(
        "core.edit.ffmpeg_renderer._mux_av"
    ) as mux:
        mux.side_effect = lambda *a, **k: out.write_bytes(b"fake")
        result = export_timeline_to_mp4(
            timeline_store,
            timeline,
            out,
            project_id=project_id,
            script_id=script_id,
            style_mode=VideoStyleMode.DYNAMIC_IMAGE,
        )
    assert composite.called
    assert result.segment_count >= 1


def test_export_timeline_rejects_missing_image(store_with_plan):
    from core.models.entities import EditClip, EditTimeline, EditVideoLayer

    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    script = store_with_plan.get_script(script_id)
    assert script
    timeline = EditTimeline(
        script_id=script_id,
        duration_ms=5000,
        video_layers=[
            EditVideoLayer(
                id="vly_main",
                clips=[
                    EditClip(
                        track="video",
                        start_ms=0,
                        end_ms=5000,
                        label="无素材",
                    )
                ],
            )
        ],
    )
    out = Path("fake_no_media.mp4")
    with patch("core.edit.ffmpeg_renderer.is_ffmpeg_available", return_value=True):
        with pytest.raises(FfmpegExportError, match="缺少可访问图片"):
            export_timeline_to_mp4(
                store_with_plan,
                timeline,
                out,
                project_id=script.project_id,
                script_id=script_id,
                style_mode=VideoStyleMode.DYNAMIC_IMAGE,
            )


def test_export_timeline_raises_friendly_message_when_ffmpeg_missing(timeline_store):
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    project_id = timeline_store._test_project_id  # type: ignore[attr-defined]
    plan = timeline_store.get_video_plan_for_script(script_id)
    assert plan
    timeline = compile_timeline_from_shots(
        timeline_store,
        script_id=script_id,
        plan=plan,
    )
    timeline_store.set_edit_timeline(timeline)
    out = Path("fake_out.mp4")

    with patch("core.edit.ffmpeg_renderer.is_ffmpeg_available", return_value=False):
        with pytest.raises(FfmpegExportError, match="未找到 FFmpeg"):
            export_timeline_to_mp4(
                timeline_store,
                timeline,
                out,
                project_id=project_id,
                script_id=script_id,
                style_mode=VideoStyleMode.DYNAMIC_IMAGE,
            )


def test_extract_ffmpeg_error_skips_version_header():
    from core.edit.ffmpeg_renderer import _extract_ffmpeg_error

    stderr = (
        "ffmpeg version 7.1-essentials_build\n"
        "  configuration: --enable-gpl\n"
        "Input #0, image2, from 'x.png':\n"
        "Error while opening encoder for output stream #0:0\n"
    )
    err = _extract_ffmpeg_error(stderr)
    assert "ffmpeg version" not in err
    assert "Error while opening encoder" in err


def test_export_timeline_rejects_same_layer_overlap(store_with_plan):
    from core.edit.timeline import normalize_tracks
    from core.models.entities import EditTimeline, MediaAsset, MediaAssetType

    script_id = store_with_plan._test_script_id  # type: ignore[attr-defined]
    media_id = store_with_plan._test_media_id  # type: ignore[attr-defined]
    shot_id = store_with_plan._test_shot_id  # type: ignore[attr-defined]
    script = store_with_plan.get_script(script_id)
    assert script
    audio = MediaAsset(
        project_id=script.project_id,
        script_id=script_id,
        type=MediaAssetType.AUDIO,
        name="旁白",
        url="https://audio.test/narration.mp3",
        metadata={"shot_id": shot_id, "duration_ms": 5000},
    )
    store_with_plan.add_media_asset(audio)
    timeline = EditTimeline(
        script_id=script_id,
        duration_ms=5000,
        tracks=normalize_tracks(
            {
                "video": [],
                "audio": [
                    {
                        "track": "audio",
                        "start_ms": 0,
                        "end_ms": 5000,
                        "asset_ref": audio.id,
                        "metadata": {"shot_id": shot_id},
                    }
                ],
                "subtitle": [],
            }
        ),
        video_layers=[
            {
                "id": "vly_main",
                "name": "主画面",
                "z_index": 0,
                "clips": [
                    {
                        "id": "clip_overlap_a",
                        "track": "video",
                        "start_ms": 0,
                        "end_ms": 4000,
                        "asset_ref": media_id,
                        "metadata": {"shot_id": shot_id},
                    },
                    {
                        "id": "clip_overlap_b",
                        "track": "video",
                        "start_ms": 3000,
                        "end_ms": 5000,
                        "asset_ref": media_id,
                        "metadata": {"shot_id": shot_id},
                    },
                ],
            }
        ],
    )
    out = Path("fake_overlap.mp4")
    with patch("core.edit.ffmpeg_renderer.is_ffmpeg_available", return_value=True):
        with pytest.raises(FfmpegExportError, match="同层 clip 重叠"):
            export_timeline_to_mp4(
                store_with_plan,
                timeline,
                out,
                project_id=script.project_id,
                script_id=script_id,
                style_mode=VideoStyleMode.DYNAMIC_IMAGE,
            )
