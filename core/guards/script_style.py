"""剧本视频风格绑定与锁定：生成剧本时确定，全链路不可修改。"""

import re

from core.llm.style.style_mode_registry import StyleModeRegistry
from core.models.entities import Project, Script, VideoStyleMode


class ScriptStyleLockedError(Exception):
    """剧本视频风格已锁定，拒绝修改为其他风格。"""

    def __init__(self, current: str, requested: str) -> None:
        self.current = current
        self.requested = requested
        super().__init__(
            f"剧本视频风格已锁定为 {current}，不可改为 {requested}"
        )


# 历史持久化数据中的旧风格 id → 现行 id（仅在边界规范化，不产生双轨逻辑）
_LEGACY_STYLE_ALIASES = {
    "dynamic_image": VideoStyleMode.STORYBOOK.value,
    "dynamic_comic": VideoStyleMode.STORYBOOK.value,
    "marketing_video": VideoStyleMode.STORYBOOK.value,
    "marketing": VideoStyleMode.STORYBOOK.value,
}


def _style_id(mode: VideoStyleMode | str | None) -> str | None:
    """将 enum 或字符串规范化为 style id（含历史别名迁移）。"""
    if mode is None:
        return None
    if isinstance(mode, VideoStyleMode):
        return mode.value
    text = str(mode).strip()
    if text in _LEGACY_STYLE_ALIASES:
        return _LEGACY_STYLE_ALIASES[text]
    for item in VideoStyleMode:
        if text == item.value:
            return item.value
    if text.startswith("VideoStyleMode."):
        name = text.split(".", 1)[-1]
        try:
            return VideoStyleMode[name].value
        except KeyError:
            pass
    return text


def normalize_style_mode_id(mode: VideoStyleMode | str | None) -> str | None:
    """对外暴露：将 style 规范化为字符串 id。"""
    return _style_id(mode)


def bind_script_style(
    script: Script,
    project: Project,
    requested: VideoStyleMode | str | None,
) -> str:
    """
    在生成剧本时绑定视频风格。
    已锁定则仅允许与当前一致；未锁定则写入并锁定。
    """
    current = _style_id(script.style_mode)
    req = _style_id(requested)
    if script.style_locked and current is not None:
        if req is not None and req != current:
            raise ScriptStyleLockedError(current, req)
        return current

    mode = req if req is not None else _style_id(project.config.style.mode)
    if mode is None:
        mode = VideoStyleMode.STORYBOOK.value
    StyleModeRegistry.validate_style_id(mode)
    script.style_mode = mode
    script.style_locked = True
    return mode


# 允许的可选通用提示词键：图片风格 / 预计时长
STYLE_HINT_KEYS = ("image_style", "target_duration")

# 提示词键的中文展示名（组装上下文时使用）
STYLE_HINT_LABELS = {"image_style": "图片风格", "target_duration": "预计时长"}


def normalize_style_hints(raw: dict[str, str] | None) -> dict[str, str]:
    """过滤可选提示词：仅保留白名单键与非空字符串值。"""
    if not isinstance(raw, dict):
        return {}
    hints: dict[str, str] = {}
    for key in STYLE_HINT_KEYS:
        value = str(raw.get(key) or "").strip()
        if value:
            hints[key] = value
    return hints


def parse_target_duration_sec(text: str) -> int | None:
    """将预计时长提示词（如「30秒」「2分钟」）解析为秒数。"""
    raw = str(text or "").strip()
    if not raw:
        return None
    normalized = raw.replace(" ", "").lower()

    minute_match = re.fullmatch(r"(\d+)(?:分钟|分|min(?:ute)?s?)", normalized)
    if minute_match:
        return int(minute_match.group(1)) * 60

    second_match = re.fullmatch(r"(\d+)(?:秒|s(?:ec)?s?)", normalized)
    if second_match:
        return int(second_match.group(1))

    if normalized.isdigit():
        return int(normalized)
    return None


def _apply_target_duration_from_hints(script: Script, hints: dict[str, str]) -> None:
    """将 style_hints 中的预计时长同步到剧本 duration_sec 字段。"""
    duration = parse_target_duration_sec(hints.get("target_duration", ""))
    if duration is not None and duration > 0:
        script.duration_sec = duration


def bind_script_style_hints(
    script: Script,
    requested: dict[str, str] | None,
) -> dict[str, str]:
    """随风格锁定绑定可选提示词；已绑定后保持不变（与风格同语义锁定）。"""
    if script.style_locked and script.style_hints:
        return dict(script.style_hints)
    hints = normalize_style_hints(requested)
    if hints:
        script.style_hints = hints
        _apply_target_duration_from_hints(script, hints)
    return dict(script.style_hints or {})


def format_style_hints_line(hints: dict[str, str] | None) -> str:
    """将可选提示词格式化为单行中文文本；为空返回空串（不组装）。"""
    normalized = normalize_style_hints(hints)
    if not normalized:
        return ""
    parts = [
        f"{STYLE_HINT_LABELS.get(key, key)}={value}"
        for key, value in normalized.items()
    ]
    return "；".join(parts)


def get_script_style(script: Script, project: Project) -> str:
    """获取剧本已绑定风格；未绑定时回退项目默认（仅初始化前）。"""
    if script.style_mode is not None:
        sid = _style_id(script.style_mode)
        return sid if sid is not None else VideoStyleMode.STORYBOOK.value
    sid = _style_id(project.config.style.mode)
    return sid if sid is not None else VideoStyleMode.STORYBOOK.value
