"""FFmpeg pad/scale 滤镜回归（Ken Burns 奇数尺寸）。"""

import subprocess
from pathlib import Path

import pytest

from core.edit.export_settings import ExportSettings
from core.edit.ffmpeg_renderer import _render_layer_source
from core.edit.transform_interp import ResolvedTransform, build_scaled_video_filter
from core.models.entities import MediaAssetType
from core.tts.ffmpeg_util import is_ffmpeg_available, resolve_ffmpeg_binary

pytestmark = pytest.mark.skipif(
    not is_ffmpeg_available(),
    reason="FFmpeg not available",
)


def _write_test_image(ffmpeg: str, path: Path) -> None:
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x50783C:s=1920x1080",
            "-frames:v",
            "1",
            str(path),
        ],
        capture_output=True,
        check=True,
    )


def test_build_scaled_video_filter_runs_without_pad_error(tmp_path: Path):
    """scale=1.125 曾导致奇数 pad 高度，FFmpeg 报 Padded dimensions cannot be smaller。"""
    ffmpeg = resolve_ffmpeg_binary()
    img_path = tmp_path / "test.png"
    _write_test_image(ffmpeg, img_path)
    out_path = tmp_path / "layer.mp4"

    transform = ResolvedTransform(
        x=0.5, y=0.5, width=1.0, height=1.0, opacity=1.0, rotation=0.0, scale=1.125
    )
    vf = build_scaled_video_filter(transform, canvas_width=1920, canvas_height=1080)
    assert "force_divisible_by=2" in vf

    _render_layer_source(
        ffmpeg=ffmpeg,
        local=img_path,
        media_type=MediaAssetType.IMAGE,
        duration_sec=0.25,
        output_path=out_path,
        settings=ExportSettings(),
        transform={
            "x": transform.x,
            "y": transform.y,
            "width": transform.width,
            "height": transform.height,
            "opacity": transform.opacity,
            "rotation": transform.rotation,
            "scale": transform.scale,
        },
        clip_id="clip_0",
    )
    assert out_path.is_file()
    assert out_path.stat().st_size > 0
