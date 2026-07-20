"""在系统文件管理器中定位已导出的成片文件。"""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path


def reveal_path_in_file_manager(path: Path) -> None:
    """在资源管理器 / Finder 中选中指定文件。"""
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"文件不存在: {resolved}")

    system = platform.system()
    if system == "Windows":
        subprocess.run(
            ["explorer", f"/select,{resolved}"],
            check=False,
        )
        return
    if system == "Darwin":
        subprocess.run(["open", "-R", str(resolved)], check=False)
        return
    subprocess.run(["xdg-open", str(resolved.parent)], check=False)
