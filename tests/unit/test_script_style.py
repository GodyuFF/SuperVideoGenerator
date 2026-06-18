"""剧本视频风格绑定与锁定测试。"""

import pytest

from core.guards.script_style import bind_script_style, ScriptStyleLockedError
from core.models.entities import Project, Script, VideoStyleMode


def test_bind_style_on_first_call():
  """首次绑定应写入 style_mode 并锁定。"""
  project = Project(title="p")
  script = Script(project_id=project.id, title="s")

  mode = bind_script_style(script, project, VideoStyleMode.AI_VIDEO)
  assert mode == VideoStyleMode.AI_VIDEO
  assert script.style_mode == VideoStyleMode.AI_VIDEO
  assert script.style_locked is True


def test_bind_style_uses_project_default_when_not_requested():
  """未指定风格时使用项目默认。"""
  project = Project(title="p")
  project.config.style.mode = VideoStyleMode.DYNAMIC_IMAGE
  script = Script(project_id=project.id, title="s")

  mode = bind_script_style(script, project, None)
  assert mode == VideoStyleMode.DYNAMIC_IMAGE
  assert script.style_locked is True


def test_cannot_change_locked_style():
  """锁定后尝试修改为其他风格应失败。"""
  project = Project(title="p")
  script = Script(project_id=project.id, title="s")
  bind_script_style(script, project, VideoStyleMode.DYNAMIC_IMAGE)

  with pytest.raises(ScriptStyleLockedError):
    bind_script_style(script, project, VideoStyleMode.AI_VIDEO)


def test_locked_style_same_mode_ok():
  """锁定后传入相同风格应允许（幂等）。"""
  project = Project(title="p")
  script = Script(project_id=project.id, title="s")
  bind_script_style(script, project, VideoStyleMode.AI_VIDEO)

  mode = bind_script_style(script, project, VideoStyleMode.AI_VIDEO)
  assert mode == VideoStyleMode.AI_VIDEO
