"""分阶段结构化日志：统一 [STAGE:模块] 格式，便于流水线调试。"""

import logging
import os
import sys
from typing import Any

# 日志阶段前缀，与产品手册中的分阶段输出一致
STAGE_PREFIX = "[STAGE"


def setup_logging(level: str | None = None) -> None:
    """初始化全局日志；可通过环境变量 LOG_LEVEL 控制级别。"""
    log_level = level or os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger。"""
    return logging.getLogger(name)


def log_stage(logger: logging.Logger, stage: str, message: str, **kwargs: Any) -> None:
    """输出带阶段标记的结构化日志行。"""
    extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
    suffix = f" {extra}" if extra else ""
    logger.info(f"{STAGE_PREFIX}:{stage}] {message}{suffix}")
