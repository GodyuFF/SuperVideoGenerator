"""NLE 工程包导出单元测试。"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from core.edit.nle_export import NleExportError, export_timeline_to_premiere_package
from core.edit.nle_export.srt_writer import write_srt
from core.models.entities import EditClip, EditTimeline
from tests.support.timeline_store_fixture import timeline_store


def test_write_srt_from_subtitle_clips(timeline_store):
    """字幕轨应正确转为 SRT。"""
    timeline = timeline_store.get_edit_timeline_for_script(timeline_store._test_script_id)  # type: ignore[attr-defined]
    assert timeline
    srt = write_srt(timeline)
    assert "00:00:" in srt
    assert "老虎" in srt or srt == ""


def test_export_premiere_package_creates_zip(timeline_store, tmp_path):
    """应生成含 project.xml 与 media 的 ZIP 工程包。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    project_id = timeline_store._test_project_id  # type: ignore[attr-defined]
    timeline = timeline_store.get_edit_timeline_for_script(script_id)
    assert timeline

    out = tmp_path / "nle_test.zip"
    result = export_timeline_to_premiere_package(
        timeline_store,
        timeline,
        out,
        project_id=project_id,
        script_id=script_id,
        sequence_name="测试序列",
    )

    assert out.is_file()
    assert result.media_count >= 1
    assert result.clip_count >= 1
    assert result.format == "fcp7_xmeml"

    with zipfile.ZipFile(out, "r") as zf:
        names = set(zf.namelist())
        assert "project.xml" in names
        assert "README.txt" in names
        assert any(n.startswith("media/") for n in names)
        xml = zf.read("project.xml").decode("utf-8")
        assert 'version="5"' in xml or "<xmeml" in xml
        assert "测试序列" in xml or script_id in xml


def test_export_premiere_package_missing_media_raises(timeline_store, tmp_path):
    """缺素材的时间轴应拒绝导出。"""
    script_id = timeline_store._test_script_id  # type: ignore[attr-defined]
    project_id = timeline_store._test_project_id  # type: ignore[attr-defined]
    timeline = timeline_store.get_edit_timeline_for_script(script_id)
    assert timeline

    broken = timeline.model_copy(
        update={
            "video_layers": [
                layer.model_copy(
                    update={
                        "clips": [
                            EditClip(
                                id="broken",
                                track="video",
                                start_ms=0,
                                end_ms=1000,
                                label="无素材",
                                asset_ref="media_missing_xxx",
                            )
                        ]
                    }
                )
                for layer in timeline.video_layers
            ]
        }
    )
    out = tmp_path / "broken.zip"
    with pytest.raises(NleExportError):
        export_timeline_to_premiere_package(
            timeline_store,
            broken,
            out,
            project_id=project_id,
            script_id=script_id,
        )
