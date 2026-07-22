"""后台 chat 编排任务：释放 HTTP 连接，通过 WebSocket 推送进度。"""

from __future__ import annotations

import asyncio
import logging
import time

from apps.api.state import AppState
from core.guards.script_style import ScriptStyleLockedError
from core.logging.perf import async_perf_span, log_perf
from core.models.entities import ScriptStatus
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
    early_failure: str | None = None
    try:
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
            except asyncio.CancelledError:
                # abort 会 cancel 任务；吞掉 CancelledError 以便完成收尾并解锁发送
                early_failure = "用户已中止执行"
                logger.info("后台 chat 被取消 script=%s", script_id)
                script = state.store.get_script(script_id)
                if script and script.status == ScriptStatus.EXECUTING:
                    script.status = ScriptStatus.FAILED
            except ScriptStyleLockedError as exc:
                early_failure = str(exc)
                logger.warning("后台 chat 风格锁定拒绝: %s", exc)
            except ValueError as exc:
                early_failure = str(exc)
                logger.warning("后台 chat 业务拒绝: %s", exc)
            except RuntimeError as exc:
                early_failure = str(exc)
                logger.error("后台 chat 运行时错误: %s", exc)
            except Exception as exc:
                early_failure = str(exc) or exc.__class__.__name__
                logger.exception("后台 chat 未处理异常")

        if early_failure:
            # 早期失败可能尚未进入 ReAct，需主动推送失败事件
            try:
                event_type = (
                    "execution_aborted"
                    if early_failure == "用户已中止执行"
                    else "execution_failed"
                )
                await state.emitter.emit(
                    {
                        "type": event_type,
                        "script_id": script_id,
                        "project_id": project_id,
                        "conversation_id": conversation_id,
                        "error": early_failure,
                    }
                )
            except Exception:
                logger.exception("后台 chat 失败事件推送失败 script=%s", script_id)

        # 无论成功/失败/早退，都推送收尾事件，避免前端 isRunning 因漏收 WS 而锁死
        try:
            await state.emitter.emit(
                {
                    "type": "chat_background_finished",
                    "script_id": script_id,
                    "project_id": project_id,
                    "conversation_id": conversation_id,
                    "ok": early_failure is None,
                    "error": early_failure,
                }
            )
        except Exception:
            logger.exception("后台 chat 收尾事件推送失败 script=%s", script_id)

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
    finally:
        state.clear_chat_task(script_id, task=asyncio.current_task())
