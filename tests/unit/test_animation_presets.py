"""animationPresets 逻辑镜像测试（与 apps/web/src/edit/animationPresets.ts 对齐）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Clip:
    start_ms: int = 0
    end_ms: int = 3000
    motion: str | None = None
    transform: dict[str, Any] = field(default_factory=dict)


def _apply_fade_in(clip: _Clip, dur: int) -> dict:
    base = {"x": 0.5, "y": 0.5, "width": 1.0, "height": 1.0, "opacity": 1.0, "rotation": 0.0}
    base.update(clip.transform)
    return {
        "keyframes": [
            {"time_ms": 0, **base, "opacity": 0},
            {"time_ms": dur, **base, "opacity": 1},
        ]
    }


def test_fade_in_keyframes():
    clip = _Clip()
    kfs = _apply_fade_in(clip, 3000)["keyframes"]
    assert kfs[0]["opacity"] == 0
    assert kfs[1]["opacity"] == 1
    assert kfs[0]["time_ms"] == 0
    assert kfs[1]["time_ms"] == 3000
