"""WhisperX 对齐优先级与 GPU 不可用时的回退测试。"""

from __future__ import annotations

from pathlib import Path

from core.edit.subtitle_align import build_cues_for_audio_media
from core.edit.whisperx_align import (
    build_cues_via_whisperx,
    is_whisperx_available,
    resolve_local_audio_path,
)
from core.models.entities import MediaAsset, MediaAssetType, Project, Script
from core.store.memory import MemoryStore


def test_is_whisperx_available_requires_cuda(monkeypatch):
    """torch.cuda 不可用时 WhisperX 路径关闭。"""
    import types
    import sys

    import core.edit.whisperx_align as mod

    fake_torch = types.ModuleType("torch")

    class _Cuda:
        @staticmethod
        def is_available() -> bool:
            return False

    fake_torch.cuda = _Cuda()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "whisperx", types.ModuleType("whisperx"))
    # 清掉可能已缓存的真实 import 行为：直接测函数本体
    assert is_whisperx_available() is False
    _ = mod


def test_resolve_local_audio_path_for_file_url(tmp_path: Path):
    """本地文件 url 可解析。"""
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    media = type("M", (), {"url": str(wav), "metadata": {}})()
    assert resolve_local_audio_path(media) == wav.resolve()


def test_build_cues_prefers_metadata_over_whisperx(monkeypatch, tmp_path: Path):
    """已有 metadata.subtitle_cues 时不调用 WhisperX。"""
    wav = tmp_path / "v.wav"
    wav.write_bytes(b"RIFF")
    store = MemoryStore()
    project = Project(title="wx")
    store.add_project(project)
    script = Script(project_id=project.id, title="s", duration_sec=30)
    store.add_script(script)
    media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.AUDIO,
        name="配音",
        url=str(wav),
        metadata={
            "duration_ms": 3000,
            "narration_text": "第一句。第二句！",
            "subtitle_cues": [{"text": "缓存句", "start_ms": 0, "end_ms": 1000}],
        },
    )
    store.add_media_asset(media)
    called = {"n": 0}

    def _fake_wx(*_a, **_k):
        called["n"] += 1
        return [{"text": "wx", "start_ms": 0, "end_ms": 500, "source": "whisperx"}]

    monkeypatch.setattr("core.edit.whisperx_align.build_cues_via_whisperx", _fake_wx)
    cues = build_cues_for_audio_media(store, media)
    assert cues[0]["text"] == "缓存句"
    assert called["n"] == 0


def test_build_cues_uses_whisperx_when_no_metadata(monkeypatch, tmp_path: Path):
    """无 cue 时走 WhisperX。"""
    wav = tmp_path / "v.wav"
    wav.write_bytes(b"RIFF")
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s", duration_sec=10)
    store.add_script(script)
    media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.AUDIO,
        name="a",
        url=str(wav),
        metadata={"duration_ms": 2000, "narration_text": "你好。世界。"},
    )
    store.add_media_asset(media)

    def _fake_via(_media, *, narration_text="", align_fn=None, allow_asr=True):
        del align_fn, allow_asr
        assert "你好" in narration_text
        return [
            {"text": "你好。", "start_ms": 0, "end_ms": 900, "source": "whisperx"},
            {"text": "世界。", "start_ms": 900, "end_ms": 2000, "source": "whisperx"},
        ]

    monkeypatch.setattr("core.edit.whisperx_align.build_cues_via_whisperx", _fake_via)
    cues = build_cues_for_audio_media(store, media, narration_text="你好。世界。")
    assert len(cues) == 2
    assert cues[0]["source"] == "whisperx"
    assert cues[1]["end_ms"] == 2000


def test_build_cues_falls_back_proportional_when_whisperx_empty(monkeypatch, tmp_path: Path):
    """WhisperX 返回空时回退字数比例。"""
    wav = tmp_path / "v.wav"
    wav.write_bytes(b"RIFF")
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s", duration_sec=10)
    store.add_script(script)
    media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.AUDIO,
        name="a",
        url=str(wav),
        metadata={"duration_ms": 3000, "narration_text": "第一句。第二句！"},
    )
    store.add_media_asset(media)
    monkeypatch.setattr(
        "core.edit.whisperx_align.build_cues_via_whisperx",
        lambda *_a, **_k: [],
    )
    cues = build_cues_for_audio_media(store, media)
    assert len(cues) >= 2
    assert cues[0]["end_ms"] > cues[0]["start_ms"]
    assert cues[-1]["end_ms"] == 3000


def test_build_cues_via_whisperx_inject_align_fn(tmp_path: Path):
    """build_cues_via_whisperx 可通过 align_fn 注入（测试隔离）。"""
    wav = tmp_path / "v.wav"
    wav.write_bytes(b"RIFF")
    media = type(
        "M",
        (),
        {
            "url": str(wav),
            "metadata": {"duration_ms": 1000, "narration_text": "测。"},
        },
    )()

    def _align(path, text, *, language=None, duration_sec=None):
        del language, duration_sec
        assert Path(path).is_file()
        assert "测" in text
        return [{"text": "测。", "start_ms": 0, "end_ms": 1000, "source": "whisperx"}]

    cues = build_cues_via_whisperx(media, align_fn=_align)
    assert cues == [{"text": "测。", "start_ms": 0, "end_ms": 1000, "source": "whisperx"}]
