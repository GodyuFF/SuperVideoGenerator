"""内置免费音效目录（CC0 / Mixkit 等可商用素材，无 API Key 时兜底）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuiltinSoundEntry:
    """单条内置音效元数据。"""

    id: int
    name: str
    description: str
    preview_url: str
    duration: float
    tags: tuple[str, ...]
    license: str
    username: str


# 负 ID 与 Freesound 正 ID 区分；preview_url 为可直接拉取的 MP3。
BUILTIN_SOUNDS: tuple[BuiltinSoundEntry, ...] = (
    BuiltinSoundEntry(
        id=-1,
        name="清脆点击",
        description="短促 UI 点击反馈",
        preview_url="https://assets.mixkit.co/active_storage/sfx/2568/2568-preview.mp3",
        duration=0.5,
        tags=("click", "ui", "interface"),
        license="Mixkit License",
        username="Mixkit",
    ),
    BuiltinSoundEntry(
        id=-2,
        name="成功提示音",
        description="轻快成就/完成提示",
        preview_url="https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3",
        duration=1.2,
        tags=("success", "notification", "achievement"),
        license="Mixkit License",
        username="Mixkit",
    ),
    BuiltinSoundEntry(
        id=-3,
        name="Whoosh 转场",
        description="快速划过转场音效",
        preview_url="https://assets.mixkit.co/active_storage/sfx/2569/2569-preview.mp3",
        duration=0.8,
        tags=("whoosh", "transition", "swoosh"),
        license="Mixkit License",
        username="Mixkit",
    ),
    BuiltinSoundEntry(
        id=-4,
        name="环境雨声",
        description="轻柔持续雨声氛围",
        preview_url="https://assets.mixkit.co/active_storage/sfx/2390/2390-preview.mp3",
        duration=8.0,
        tags=("rain", "ambient", "weather", "background"),
        license="Mixkit License",
        username="Mixkit",
    ),
    BuiltinSoundEntry(
        id=-5,
        name="城市环境",
        description="远处车流与城市氛围",
        preview_url="https://assets.mixkit.co/active_storage/sfx/2474/2474-preview.mp3",
        duration=6.0,
        tags=("city", "ambient", "urban", "background"),
        license="Mixkit License",
        username="Mixkit",
    ),
    BuiltinSoundEntry(
        id=-6,
        name="脚步声",
        description="木地板上的行走脚步",
        preview_url="https://assets.mixkit.co/active_storage/sfx/2570/2570-preview.mp3",
        duration=2.0,
        tags=("footsteps", "walk", "foley"),
        license="Mixkit License",
        username="Mixkit",
    ),
    BuiltinSoundEntry(
        id=-7,
        name="开门",
        description="室内木门开启",
        preview_url="https://assets.mixkit.co/active_storage/sfx/2573/2573-preview.mp3",
        duration=1.0,
        tags=("door", "open", "foley"),
        license="Mixkit License",
        username="Mixkit",
    ),
    BuiltinSoundEntry(
        id=-8,
        name="键盘打字",
        description="机械键盘敲击",
        preview_url="https://assets.mixkit.co/active_storage/sfx/2574/2574-preview.mp3",
        duration=3.0,
        tags=("keyboard", "typing", "office"),
        license="Mixkit License",
        username="Mixkit",
    ),
    BuiltinSoundEntry(
        id=-9,
        name="人群欢呼",
        description="观众鼓掌与欢呼",
        preview_url="https://assets.mixkit.co/active_storage/sfx/2575/2575-preview.mp3",
        duration=3.5,
        tags=("crowd", "cheer", "applause", "audience"),
        license="Mixkit License",
        username="Mixkit",
    ),
    BuiltinSoundEntry(
        id=-10,
        name="风声",
        description="户外风声氛围",
        preview_url="https://assets.mixkit.co/active_storage/sfx/2576/2576-preview.mp3",
        duration=5.0,
        tags=("wind", "ambient", "nature", "background"),
        license="Mixkit License",
        username="Mixkit",
    ),
    BuiltinSoundEntry(
        id=-11,
        name="错误提示",
        description="短促否定/错误反馈",
        preview_url="https://assets.mixkit.co/active_storage/sfx/2577/2577-preview.mp3",
        duration=0.6,
        tags=("error", "fail", "notification"),
        license="Mixkit License",
        username="Mixkit",
    ),
    BuiltinSoundEntry(
        id=-12,
        name="悬疑氛围",
        description="低张力悬疑背景垫乐",
        preview_url="https://assets.mixkit.co/active_storage/sfx/2578/2578-preview.mp3",
        duration=10.0,
        tags=("suspense", "ambient", "cinematic", "background"),
        license="Mixkit License",
        username="Mixkit",
    ),
)

_BUILTIN_BY_ID = {entry.id: entry for entry in BUILTIN_SOUNDS}


def get_builtin_sound(sound_id: int) -> BuiltinSoundEntry | None:
    """按内置音效 ID 查询。"""
    return _BUILTIN_BY_ID.get(sound_id)


def search_builtin_sounds(
    query: str = "",
    *,
    commercial_only: bool = True,
    sort: str = "downloads",
) -> list[BuiltinSoundEntry]:
    """在内置目录中按关键词匹配（commercial_only 对 Mixkit 素材恒为可商用）。"""
    del commercial_only
    q = query.strip().lower()
    pool = list(BUILTIN_SOUNDS)
    if q:
        filtered: list[BuiltinSoundEntry] = []
        for entry in pool:
            hay = " ".join(
                [
                    entry.name.lower(),
                    entry.description.lower(),
                    " ".join(entry.tags),
                ]
            )
            if q in hay or any(part in hay for part in q.split() if len(part) >= 2):
                filtered.append(entry)
        pool = filtered
    if sort == "downloads":
        return pool
    return pool
