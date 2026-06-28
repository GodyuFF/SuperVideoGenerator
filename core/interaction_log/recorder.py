"""交互记录写入与 WebSocket 推送。"""

from typing import Any

from core.events.emitter import EventEmitter
from core.interaction_log.file_store import InteractionFileStore
from core.interaction_log.models import InteractionRecord
from core.interaction_log.store import InteractionLogStore
from core.logging.setup import get_logger, log_stage

logger = get_logger("core.interaction_log")


class InteractionRecorder:
    """统一记录接口交互并持久化。"""

    def __init__(
        self,
        store: InteractionLogStore,
        emitter: EventEmitter | None = None,
        file_store: InteractionFileStore | None = None,
        emit_ws_events: bool = False,
    ) -> None:
        self._store = store
        self._emitter = emitter
        self._file_store = file_store
        self._emit_ws_events = emit_ws_events

    @property
    def store(self) -> InteractionLogStore:
        return self._store

    async def record(self, record: InteractionRecord) -> InteractionRecord:
        saved = self._store.append(record)
        if self._file_store:
            self._file_store.append(saved)
        log_stage(
            logger,
            "interaction",
            saved.summary or saved.kind,
            kind=saved.kind,
            source=saved.source,
            script_id=saved.script_id or "-",
        )
        if self._emitter and self._emit_ws_events:
            await self._emitter.emit(
                {
                    "type": "interaction_log",
                    "script_id": saved.script_id,
                    "project_id": saved.project_id,
                    "record": saved.model_dump(),
                }
            )
        return saved

    async def record_agent_action(
        self,
        *,
        script_id: str,
        project_id: str = "",
        agent_name: str,
        step_id: str,
        action: str,
        observation: str,
    ) -> InteractionRecord:
        return await self.record(
            InteractionRecord(
                kind="agent_action",
                source="agent",
                project_id=project_id,
                script_id=script_id,
                agent_name=agent_name,
                step_id=step_id,
                summary=f"执行 {action}",
                response_body=observation,
                meta={"action": action},
            )
        )

    async def record_conversation_token_round(
        self,
        *,
        project_id: str,
        script_id: str,
        conversation_id: str,
        usage: dict[str, Any],
    ) -> InteractionRecord:
        total = int(usage.get("total_tokens", 0))
        model_parts = [
            f"{m.get('model')}:{m.get('total_tokens')}"
            for m in usage.get("models", [])
        ]
        summary = f"对话轮次 token 预估 {total}"
        if model_parts:
            summary += f" ({', '.join(model_parts)})"
        return await self.record(
            InteractionRecord(
                kind="conversation_token_round",
                source="llm",
                project_id=project_id,
                script_id=script_id,
                summary=summary,
                meta={
                    "conversation_id": conversation_id,
                    "token_usage": usage,
                },
            )
        )

    async def record_api_request(
        self,
        *,
        method: str,
        url: str,
        status_code: int,
        duration_ms: float,
        request_body: dict[str, Any] | None = None,
        script_id: str = "",
        project_id: str = "",
    ) -> InteractionRecord:
        return await self.record(
            InteractionRecord(
                kind="api_request",
                source="http",
                method=method,
                url=url,
                status_code=status_code,
                duration_ms=duration_ms,
                project_id=project_id,
                script_id=script_id,
                summary=f"{method} {url} → {status_code}",
                request_body=request_body,
            )
        )
