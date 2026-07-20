# -*- coding: utf-8 -*-
"""分镜剪辑轴摘要工具自检（调用 Node strip-types）。"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SELFTEST = ROOT / "apps" / "web" / "src" / "utils" / "editTimelineSummary.selftest.ts"


@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node")
def test_edit_timeline_summary_selftest():
    """前端 editTimelineSummary 门控与摘要构建应通过自检。"""
    result = subprocess.run(
        ["node", "--experimental-strip-types", str(SELFTEST)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.fail(
            f"selftest failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    assert "ok" in result.stdout
