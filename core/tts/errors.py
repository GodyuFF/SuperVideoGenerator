"""TTS 合成错误类型。"""

from __future__ import annotations


class TtsSynthesisError(Exception):
    """单次 TTS 合成失败。"""


class TtsAbortError(Exception):
    """配音合成在最大重试后仍失败，中止子 Agent / 主编排步骤。"""

    def __init__(self, action: str, message: str) -> None:
        self.action = action
        super().__init__(message)
