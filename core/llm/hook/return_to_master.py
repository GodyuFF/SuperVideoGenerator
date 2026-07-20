"""子 Agent 向主编排返回并请求协调的统一异常。"""

from __future__ import annotations

from typing import Any


class ReturnToMasterError(Exception):
    """子 Agent 暂停执行，将结构化结果交还主编排。"""

    def __init__(
        self,
        action: str,
        message: str,
        *,
        reason: str = "missing_upstream",
        structured: dict[str, Any] | None = None,
        validation_report: Any | None = None,
    ) -> None:
        self.action = action
        self.reason = reason
        self.structured = structured or {}
        self.validation_report = validation_report
        super().__init__(message)

    def to_master_observation(self) -> str:
        header = f"【return_to_master · {self.reason}】\n{self}"
        resume = self.structured.get("resume_hint")
        if resume:
            header += f"\n\n续跑提示：{resume}"
        suggested = self.structured.get("suggested_agent_ids")
        if suggested:
            header += f"\n\n建议主编排 agent_id：{', '.join(suggested)}"
        return header

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "action": self.action,
            "reason": self.reason,
            "message": str(self),
            **self.structured,
        }
        if self.validation_report is not None and hasattr(
            self.validation_report, "to_dict"
        ):
            payload["validation_report"] = self.validation_report.to_dict()
        return payload
