"""剧本视频风格绑定与锁定：生成剧本时确定，全链路不可修改。"""

from core.models.entities import Project, Script, VideoStyleMode


class ScriptStyleLockedError(Exception):
    """剧本视频风格已锁定，拒绝修改为其他风格。"""

    def __init__(self, current: VideoStyleMode, requested: VideoStyleMode) -> None:
        self.current = current
        self.requested = requested
        super().__init__(
            f"剧本视频风格已锁定为 {current.value}，不可改为 {requested.value}"
        )


def bind_script_style(
    script: Script,
    project: Project,
    requested: VideoStyleMode | None,
) -> VideoStyleMode:
    """
    在生成剧本时绑定视频风格。
    已锁定则仅允许与当前一致；未锁定则写入并锁定。
    """
    if script.style_locked and script.style_mode is not None:
        if requested is not None and requested != script.style_mode:
            raise ScriptStyleLockedError(script.style_mode, requested)
        return script.style_mode

    mode = requested if requested is not None else project.config.style.mode
    script.style_mode = mode
    script.style_locked = True
    return mode


def get_script_style(script: Script, project: Project) -> VideoStyleMode:
    """获取剧本已绑定风格；未绑定时回退项目默认（仅初始化前）。"""
    if script.style_mode is not None:
        return script.style_mode
    return project.config.style.mode
