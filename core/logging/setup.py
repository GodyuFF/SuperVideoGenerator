"""分阶段结构化日志：统一 [STAGE:模块] 格式，便于流水线调试。"""

import logging
import multiprocessing
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# 日志阶段前缀，与产品手册中的分阶段输出一致
STAGE_PREFIX = "[STAGE"
DEFAULT_LOG_FILE = Path("data/logs/app.log")


class SafeRotatingFileHandler(RotatingFileHandler):
    """Windows 友好：轮转时若文件被其它进程占用则跳过，避免刷屏 PermissionError。"""

    def doRollover(self) -> None:
        try:
            super().doRollover()
        except (PermissionError, OSError):
            # WinError 32: uvicorn reload 父/子进程或 IDE 尾随行占用日志文件
            pass

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except (PermissionError, OSError):
            self.handleError(record)


def _reload_enabled() -> bool:
    if os.environ.get("UVICORN_RELOAD", "").lower() in ("1", "true", "yes"):
        return True
    return any(arg == "--reload" or arg.startswith("--reload=") for arg in sys.argv)


def _should_attach_file_handler() -> bool:
    log_file = os.environ.get("LOG_FILE", str(DEFAULT_LOG_FILE))
    if not log_file or log_file.lower() in ("0", "false", "off", "none"):
        return False
    # uvicorn --reload 时父进程（MainProcess）不写轮转文件，避免与子进程争用句柄
    if _reload_enabled() and multiprocessing.current_process().name == "MainProcess":
        return False
    return True


def setup_logging(level: str | None = None) -> None:
    """初始化全局日志；可通过环境变量 LOG_LEVEL 控制级别。"""
    log_level = level or os.environ.get("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(log_level)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    if _should_attach_file_handler():
        log_file = os.environ.get("LOG_FILE", str(DEFAULT_LOG_FILE))
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = SafeRotatingFileHandler(
            path,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
            delay=True,
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger。"""
    return logging.getLogger(name)


def log_stage(logger: logging.Logger, stage: str, message: str, **kwargs: Any) -> None:
    """输出带阶段标记的结构化日志行。"""
    extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
    suffix = f" {extra}" if extra else ""
    logger.info(f"{STAGE_PREFIX}:{stage}] {message}{suffix}")
