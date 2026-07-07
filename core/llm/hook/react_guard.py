"""ReAct 循环守卫：检测连续相同工具 + 相同参数的重复调用。"""

from __future__ import annotations

import json
from typing import Any

from core.tts.errors import TtsAbortError, TtsSynthesisError
from core.llm.hook.return_to_master import ReturnToMasterError


class DuplicateActionAbortError(Exception):
    """子 Agent 因连续重复调用相同工具与参数而中止。"""

    def __init__(self, action: str, message: str) -> None:
        self.action = action
        super().__init__(message)


class ImageGenerationAbortError(Exception):
    """图片生成在最大重试次数后仍失败，中止子 Agent / 主编排步骤。"""

    def __init__(
        self,
        action: str,
        message: str,
        *,
        failure_analysis: Any | None = None,
    ) -> None:
        self.action = action
        self.failure_analysis = failure_analysis
        super().__init__(message)

    def needs_upstream_prompt_adjustment(self) -> bool:
        analysis = self.failure_analysis
        if analysis is None:
            return False
        checker = getattr(analysis, "needs_upstream_prompt_adjustment", None)
        if callable(checker):
            return bool(checker())
        return False


class EditComposeMissingAssetsError(ReturnToMasterError):
    """剪辑素材不齐，中止子 Agent / 触发主编排重委派上游。"""

    def __init__(
        self,
        action: str,
        message: str,
        *,
        validation_report: Any | None = None,
    ) -> None:
        structured: dict[str, Any] = {}
        suggested: list[str] = []
        if validation_report is not None:
            for item in getattr(validation_report, "missing_items", []) or []:
                upstream = getattr(item, "suggested_upstream", None)
                if upstream and upstream != "none":
                    delegate = f"delegate_{upstream}"
                    if delegate not in suggested:
                        suggested.append(delegate)
            structured["missing_items"] = [
                {
                    "category": getattr(m, "category", ""),
                    "clip_id": getattr(m, "clip_id", ""),
                    "reason": getattr(m, "reason", ""),
                    "suggested_upstream": getattr(m, "suggested_upstream", ""),
                }
                for m in getattr(validation_report, "missing_items", []) or []
            ]
        if suggested:
            structured["suggested_delegates"] = suggested
        structured["resume_hint"] = "上游补全后重新 delegate_edit_compose"
        super().__init__(
            action,
            message,
            reason="missing_upstream",
            structured=structured,
            validation_report=validation_report,
        )


def action_signature(action: str, action_input: dict[str, Any] | None) -> str:
    """稳定序列化 action + input，用于重复检测。"""
    payload = {"action": action, "input": action_input or {}}
    return json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)


def is_consecutive_duplicate_action(previous: str | None, signature: str) -> bool:
    """仅当与上一次调用签名相同时视为重复。"""
    return previous is not None and previous == signature


class ReActLoopGuard:
    """记录上一次 action 签名；连续第 2 次相同签名返回中止 observation。"""

    def __init__(self) -> None:
        self._last_signature: str | None = None

    def record(self, action: str, action_input: dict[str, Any] | None) -> str | None:
        """若与上一次连续重复则返回中止 observation，否则更新并返回 None。"""
        signature = action_signature(action, action_input)
        if is_consecutive_duplicate_action(self._last_signature, signature):
            return f"重复调用 {action}（连续相同参数），子 Agent 已中止。"
        self._last_signature = signature
        return None


__all__ = [
    "DuplicateActionAbortError",
    "EditComposeMissingAssetsError",
    "ImageGenerationAbortError",
    "ReActLoopGuard",
    "TtsAbortError",
    "TtsSynthesisError",
    "action_signature",
    "is_consecutive_duplicate_action",
]
