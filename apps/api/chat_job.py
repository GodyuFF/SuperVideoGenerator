"""后台 chat 编排任务：释放 HTTP 连接，通过 WebSocket 推送进度。"""

from __future__ import annotations

import logging
import time

from apps.api.state import AppState
from core.guards.script_style import ScriptStyleLockedError
from core.logging.perf import async_perf_span, log_perf
from core.store.persist import flush_coalesced_execution_save

logger = logging.getLogger(__name__)


async def run_chat_background(
    state: AppState,
    *,
    project_id: str,
    script_id: str,
    conversation_id: str,
    message: str,
    requested_style: str | None,
    requested_hints: dict[str, str] | None = None,
    execution_mode: str | None = None,
    skill_id: str | None = None,
) -> None:
    """在后台执行主编排并在结束时落盘。"""
    chat_start = time.perf_counter()
    async with async_perf_span(
        "chat",
        "run_from_message",
        logger=logger,
        project_id=project_id,
        script_id=script_id,
        conversation_id=conversation_id,
    ):
        try:
            await state.super_video_master.run_from_message(
                project_id,
                script_id,
                message,
                requested_style=requested_style,
                requested_hints=requested_hints,
                conversation_id=conversation_id,
                execution_mode=execution_mode,
                skill_id=skill_id,
            )
        except ScriptStyleLockedError as exc:
            logger.warning("后台 chat 风格锁定拒绝: %s", exc)
        except ValueError as exc:
            logger.warning("后台 chat 业务拒绝: %s", exc)
        except RuntimeError as exc:
            logger.error("后台 chat 运行时错误: %s", exc)
        except Exception:
            logger.exception("后台 chat 未处理异常")
    persist_start = time.perf_counter()
    flush_coalesced_execution_save(
        state.store,
        conversation_index=state.conversation_index,
        conversation_store=state.conversations,
    )
    await state.conversation_write_queue.drain()
    await state.persist_store_async(immediate=True)
    persist_ms = (time.perf_counter() - persist_start) * 1000
    total_ms = (time.perf_counter() - chat_start) * 1000
    log_perf(
        "chat",
        "后台 chat 结束",
        duration_ms=total_ms,
        logger=logger,
        project_id=project_id,
        script_id=script_id,
        conversation_id=conversation_id,
        persist_ms=round(persist_ms, 1),
    )
    state.clear_chat_task(script_id)
