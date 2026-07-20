"""剪辑合成缺失素材异常与主编排 observation 格式化。"""

from __future__ import annotations

from typing import Any

from core.edit.asset_resolver import EditTimelineValidationReport, MissingItem


class EditComposeMissingAssetsError(Exception):
    """剪辑计划稿素材不齐，需上报主编排并可能重委派上游。"""

    def __init__(
        self,
        action: str,
        message: str,
        *,
        validation_report: EditTimelineValidationReport | None = None,
    ) -> None:
        self.action = action
        self.validation_report = validation_report
        super().__init__(message)


def upstream_steps_to_redo(missing_items: list[MissingItem]) -> list[str]:
    """从缺失项推导需重新开放的 pipeline step_type。"""
    mapping = {
        "script_design": "script_design",
        "image_gen": "image_gen",
        "tts_gen": "tts_gen",
        "storyboard": "storyboard",
    }
    steps: list[str] = []
    for item in missing_items:
        up = item.suggested_upstream
        if up in mapping and mapping[up] not in steps:
            steps.append(mapping[up])
    return steps


def format_edit_compose_failure_observation(
    report: EditTimelineValidationReport,
    *,
    agent_display_name: str = "剪辑 Agent",
    step_title: str = "剪辑合成",
) -> str:
    lines = [
        f"委派 {agent_display_name} 失败：步骤「{step_title}」素材不齐。",
        "",
        "【剪辑缺失明细】",
    ]
    for i, item in enumerate(report.missing_items[:20], start=1):
        parts = [
            f"{i}. [{item.category}] clip={item.clip_id or '-'}",
            item.reason,
        ]
        if item.shot_id:
            parts.append(f"shot={item.shot_id}")
        if item.text_asset_id:
            parts.append(f"text_asset={item.text_asset_id}")
        parts.append(f"建议上游={item.suggested_upstream}")
        lines.append(" · ".join(parts))

    from core.llm.master.actions import STEP_META

    redo = upstream_steps_to_redo(report.missing_items)
    if redo:
        lines.append("")
        lines.append(
            f"建议主编排依次委派：{', '.join(STEP_META.get(s, {}).get('agent', s) for s in redo)}，"
            "再 delegate_agent(agent_id=editing_agent)。"
        )
    return "\n".join(lines)


def validation_report_from_structured(
    data: dict[str, Any] | None,
) -> EditTimelineValidationReport | None:
    if not data or not isinstance(data, dict):
        return None
    if "missing_items" not in data:
        return None

    items: list[MissingItem] = []
    for raw in data.get("missing_items") or []:
        if not isinstance(raw, dict):
            continue
        items.append(
            MissingItem(
                category=raw.get("category", "image"),  # type: ignore[arg-type]
                clip_id=str(raw.get("clip_id", "")),
                reason=str(raw.get("reason", "")),
                suggested_upstream=raw.get("suggested_upstream", "image_gen"),  # type: ignore[arg-type]
                shot_id=str(raw.get("shot_id", "")),
                text_asset_id=str(raw.get("text_asset_id", "")),
                track=str(raw.get("track", "")),
            )
        )
    return EditTimelineValidationReport(
        ready=bool(data.get("ready")),
        missing_items=items,
        summary=dict(data.get("summary") or {}),
    )
