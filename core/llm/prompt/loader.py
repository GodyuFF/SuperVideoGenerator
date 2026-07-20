"""从 core/llm/prompt 目录加载 .md 提示词文件。"""

from functools import lru_cache
from pathlib import Path

_PROMPT_ROOT = Path(__file__).resolve().parent


def prompt_root() -> Path:
    return _PROMPT_ROOT


@lru_cache(maxsize=256)
def load_text(relative_path: str) -> str:
    """加载相对 prompt 根目录的文本文件；缺失时返回空字符串。"""
    path = _PROMPT_ROOT / relative_path
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def load_required(relative_path: str) -> str:
    text = load_text(relative_path)
    if not text:
        raise FileNotFoundError(f"缺少提示词文件: {_PROMPT_ROOT / relative_path}")
    return text


def clear_prompt_cache() -> None:
    """清空提示词文件 LRU 缓存（配置保存后调用）。"""
    load_text.cache_clear()
