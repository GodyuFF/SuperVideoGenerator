"""分阶段结构化日志：统一 [STAGE:模块] 格式，便于流水线调试。"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# 日志阶段前缀，与产品手册中的分阶段输出一致
STAGE_PREFIX = "[STAGE"
DEFAULT_LOG_FILE = Path("data/logs/app.log")


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

    log_file = os.environ.get("LOG_FILE", str(DEFAULT_LOG_FILE))
    if log_file and log_file.lower() not in ("0", "false", "off", "none"):
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            path,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
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
