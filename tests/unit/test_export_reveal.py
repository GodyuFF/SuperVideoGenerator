"""导出文件在资源管理器中定位。"""

from pathlib import Path
from unittest.mock import patch

import pytest

from core.edit.export_reveal import reveal_path_in_file_manager


def test_reveal_path_missing_file(tmp_path: Path) -> None:
    """文件不存在时应抛出 FileNotFoundError。"""
    missing = tmp_path / "missing.mp4"
    with pytest.raises(FileNotFoundError):
        reveal_path_in_file_manager(missing)


def test_reveal_path_windows(tmp_path: Path) -> None:
    """Windows 下应调用 explorer /select。"""
    target = tmp_path / "final_test.mp4"
    target.write_bytes(b"mp4")
    with patch("core.edit.export_reveal.platform.system", return_value="Windows"), patch(
        "core.edit.export_reveal.subprocess.run"
    ) as run_mock:
        reveal_path_in_file_manager(target)
    run_mock.assert_called_once()
    args = run_mock.call_args[0][0]
    assert args[0] == "explorer"
    assert "/select," in args[1]
