"""将圆软小夜枭 SVG 导出为方正品牌标 PNG / ICO（委托 Node + sharp）。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve().with_name("export_owl_icon.mjs")


def main() -> None:
    """调用 export_owl_icon.mjs 栅格化 icon.svg。"""
    if not SCRIPT.is_file():
        raise SystemExit(f"missing: {SCRIPT}")
    proc = subprocess.run(
        ["node", str(SCRIPT)],
        cwd=str(ROOT),
        check=False,
    )
    raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
