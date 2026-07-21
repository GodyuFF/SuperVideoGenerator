"""混合 reopen 意图判定：正则短路 + 条件 LLM，失败保守不重开。"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from core.llm.master.pipeline_progress import (
    _FULL_REDO_RE,
    _DOWNSTREAM_INVALIDATE,
    detect_reopen_steps,
)
from core.llm.model.chat_message import ChatMessage
from core.llm.model.llm_request import LlmRequest
from core.llm.prompt.loader import load_text
from core.models.entities import VideoStyleMode

if TYPE_CHECKING:
    from core.llm.client.client import LLMClient

logger = logging.getLogger(__name__)

VALID_STEP_TYPES = frozenset(
    {
        "script_design",
        "storyboard",
        "image_gen",
        "tts_gen",
        "shot_detail",
        "video_gen",
        "edit_compose",
    }
)

# 意图 LLM 超时（秒）；失败则保守不 reopen
_REOPEN_LLM_TIMEOUT_SEC = 20.0


@dataclass
class ReopenIntent:
    """用户重开/续跑意图判定结果。"""

    source: str = "none"
    full_redo: bool = False
    reopen_steps: list[str] = field(default_factory=list)
    resume_target: str | None = None
    reason: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """序列化为可写入 session.extra / 状态 JSON 的字典。"""
        return asdict(self)


def apply_reopen_intent_to_completed(
    completed: set[str],
    intent: ReopenIntent,
) -> set[str]:
    """按意图从完成集剔除 full_redo / reopen 步及其下游。"""
    if intent.full_redo:
        return set()
    out = set(completed)
    for step in intent.reopen_steps:
        out.discard(step)
        for dep in _DOWNSTREAM_INVALIDATE.get(step, ()):
            out.discard(dep)
    return out


def _normalize_steps(raw: Any) -> list[str]:
    """过滤非法 step_type，保序去重。"""
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        step = str(item or "").strip()
        if step not in VALID_STEP_TYPES or step in seen:
            continue
        seen.add(step)
        out.append(step)
    return out


def _normalize_resume_target(raw: Any) -> str | None:
    """校验 resume_target 是否为合法 step。"""
    if raw is None:
        return None
    step = str(raw).strip()
    if step not in VALID_STEP_TYPES:
        return None
    return step


def parse_reopen_intent_payload(
    raw: dict[str, Any],
    *,
    source: str = "llm",
) -> ReopenIntent:
    """将 LLM/字典载荷解析为 ReopenIntent（非法字段安全默认）。"""
    full_redo = bool(raw.get("full_redo", False))
    steps = _normalize_steps(raw.get("reopen_steps"))
    resume = _normalize_resume_target(raw.get("resume_target"))
    reason = str(raw.get("reason") or "").strip()
    return ReopenIntent(
        source=source,
        full_redo=full_redo,
        reopen_steps=steps,
        resume_target=resume,
        reason=reason,
        error=None,
    )


def _build_llm_system() -> str:
    """加载意图判定 system 提示；缺失时用内联兜底。"""
    fixed = load_text("agents/super_video_master/fixed/reopen_intent.md")
    if fixed.strip():
        return fixed.strip()
    return (
        "你是流水线步骤重开意图判定器。根据用户消息与已完成步骤，"
        "输出 JSON：full_redo、reopen_steps、resume_target、reason。"
        "仅在用户明确要求重做/续跑时填 reopen_steps；否则留空。"
    )


def _build_llm_user(
    user_message: str,
    progress: dict[str, Any],
    style_mode: VideoStyleMode,
) -> str:
    """构造意图判定 user 载荷（短上下文）。"""
    text = (user_message or "").strip()
    if len(text) > 2000:
        text = text[:2000]
    gaps = progress.get("gaps") or []
    if isinstance(gaps, list) and len(gaps) > 5:
        gaps = gaps[:5]
    payload = {
        "user_message": text,
        "style_mode": getattr(style_mode, "value", str(style_mode)),
        "inferred_completed_steps": progress.get("inferred_completed_steps") or [],
        "gaps": gaps,
        "valid_steps": sorted(VALID_STEP_TYPES),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


async def _call_reopen_llm(
    llm_client: LLMClient,
    user_message: str,
    progress: dict[str, Any],
    style_mode: VideoStyleMode,
) -> ReopenIntent:
    """调用轻量 LLM；超时或异常返回 source=none。"""
    request = LlmRequest(
        system=_build_llm_system(),
        messages=[
            ChatMessage(
                role="user",
                content=_build_llm_user(user_message, progress, style_mode),
            )
        ],
    )
    try:
        raw = await asyncio.wait_for(
            llm_client.complete_json(
                request,
                log_context={"role": "reopen_intent"},
                summary_prefix="reopen intent",
            ),
            timeout=_REOPEN_LLM_TIMEOUT_SEC,
        )
    except Exception as exc:  # noqa: BLE001 — 失败保守
        logger.info("reopen intent LLM failed: %s", exc)
        return ReopenIntent(
            source="none",
            error=f"{type(exc).__name__}: {exc}"[:240],
        )
    if not isinstance(raw, dict):
        return ReopenIntent(source="none", error="reopen intent 非对象 JSON")
    return parse_reopen_intent_payload(raw, source="llm")


async def resolve_reopen_intent(
    user_message: str,
    progress: dict[str, Any],
    style_mode: VideoStyleMode,
    llm_client: LLMClient | None = None,
) -> ReopenIntent:
    """
    解析用户重开意图。

    优先级：全部重做正则 → 逐步 reopen 正则 →（有完成步且有客户端）LLM → none。
    """
    text = (user_message or "").strip()
    if not text:
        return ReopenIntent(source="none")

    if _FULL_REDO_RE.search(text):
        return ReopenIntent(
            source="regex",
            full_redo=True,
            reason="用户要求全部重做",
        )

    regex_steps = sorted(detect_reopen_steps(text))
    if regex_steps:
        return ReopenIntent(
            source="regex",
            reopen_steps=regex_steps,
            reason="正则命中明确重做/续跑话术",
        )

    inferred = progress.get("inferred_completed_steps") or []
    if not inferred:
        return ReopenIntent(source="none")

    if llm_client is None:
        return ReopenIntent(source="none")

    return await _call_reopen_llm(llm_client, text, progress, style_mode)
