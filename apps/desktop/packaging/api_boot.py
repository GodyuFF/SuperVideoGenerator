"""桌面安装包 API 入口：配置路径后启动 uvicorn。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    """将 runtime/src 加入 path 并监听 127.0.0.1:8000。"""
    runtime = Path(__file__).resolve().parent
    src = runtime / "src"
    sys.path.insert(0, str(src))
    os.environ.setdefault("SVG_DESKTOP_PACKAGED", "1")
    web = runtime / "web"
    if web.is_dir():
        os.environ.setdefault("SVG_DESKTOP_WEB_ROOT", str(web))

    import uvicorn

    uvicorn.run("apps.api.main:app", host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
