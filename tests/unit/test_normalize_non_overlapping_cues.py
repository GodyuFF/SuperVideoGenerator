"""字幕非重叠规范化单元测试。"""

from core.tts.subtitle import normalize_non_overlapping_cues


def test_normalize_clips_earlier_end_when_overlap():
    """重叠时截断前一条终点至后一条起点。"""
    cues = [
        {"text": "A", "start_ms": 0, "end_ms": 8860},
        {"text": "B", "start_ms": 5000, "end_ms": 8860},
    ]
    out = normalize_non_overlapping_cues(cues)
    assert len(out) == 2
    assert out[0] == {"text": "A", "start_ms": 0, "end_ms": 5000}
    assert out[1]["text"] == "B"
    assert out[1]["start_ms"] == 5000
    assert out[1]["end_ms"] == 8860


def test_normalize_drops_zero_length_after_clip():
    """截断后时长过短的条目应丢弃。"""
    cues = [
        {"text": "A", "start_ms": 0, "end_ms": 100},
        {"text": "B", "start_ms": 0, "end_ms": 200},
    ]
    out = normalize_non_overlapping_cues(cues)
    assert len(out) == 1
    assert out[0]["text"] == "B"


def test_normalize_already_sequential_unchanged():
    """本不重叠时保持原样。"""
    cues = [
        {"text": "A", "start_ms": 0, "end_ms": 1000},
        {"text": "B", "start_ms": 1000, "end_ms": 2000},
    ]
    assert normalize_non_overlapping_cues(cues) == cues
