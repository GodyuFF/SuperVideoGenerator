"""subtitle_burn ASS 生成与烧录测试。"""

from pathlib import Path

import pytest

from core.edit.export_settings import ExportSettings
from core.edit.subtitle_burn import (
    _escape_ass_text,
    _ms_to_ass_time,
    build_ass_from_subtitle_clips,
    write_ass_file,
)
from core.models.entities import EditClip


def test_ms_to_ass_time():
    assert _ms_to_ass_time(0) == "0:00:00.00"
    assert _ms_to_ass_time(1500) == "0:00:01.50"
    assert _ms_to_ass_time(65000) == "0:01:05.00"


def test_escape_ass_text():
    assert _escape_ass_text("hello") == "hello"
    assert _escape_ass_text("a\\b") == r"a\\b"
    assert _escape_ass_text("line1\nline2") == r"line1\Nline2"
    assert _escape_ass_text("{bold}") == r"\{bold\}"


def test_build_ass_from_subtitle_clips():
    clips = [
        EditClip(
            track="subtitle",
            start_ms=0,
            end_ms=3000,
            label="老虎在雪原上",
        ),
        EditClip(
            track="subtitle",
            start_ms=3000,
            end_ms=6000,
            label="",
        ),
    ]
    ass = build_ass_from_subtitle_clips(clips, width=1920, height=1080, font_name="TestFont")
    assert "PlayResX: 1920" in ass
    assert "TestFont" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:03.00,Default,,0,0,0,,老虎在雪原上" in ass
    assert ass.count("Dialogue:") == 1


def test_write_ass_file_skips_empty(tmp_path: Path):
    clips = [
        EditClip(track="subtitle", start_ms=0, end_ms=1000, label="  "),
    ]
    path = tmp_path / "empty.ass"
    assert write_ass_file(clips, path, ExportSettings()) is False
    assert not path.is_file()


def test_write_ass_file_writes_utf8_bom(tmp_path: Path):
    clips = [
        EditClip(track="subtitle", start_ms=0, end_ms=2000, label="旁白测试"),
    ]
    path = tmp_path / "subs.ass"
    assert write_ass_file(clips, path, ExportSettings()) is True
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "旁白测试" in path.read_text(encoding="utf-8-sig")
