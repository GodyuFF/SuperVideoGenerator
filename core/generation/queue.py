"""图片/视频统一生成队列实现。"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Awaitable, Callable

from core.generation.models import (
    GenerationJob,
    GenerationKind,
    GenerationSource,
    GenerationStatus,
    new_job_id,
)

_RECENT_MAX = 50


class GenerationQueue:
    """进程内全局串行生成队列，同一时刻仅一条 running。"""

    def __init__(self) -> None:
        self._pending: deque[str] = deque()
        self._jobs: dict[str, GenerationJob] = {}
        self._recent: deque[str] = deque(maxlen=_RECENT_MAX)
        self._active_id: str | None = None
        self._runner: Callable[[GenerationJob], Awaitable[None]] | None = None
        self._worker_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._on_change: Callable[[str], Awaitable[None]] | None = None
        self._done_events: dict[str, asyncio.Event] = {}

    def set_runner(self, runner: Callable[[GenerationJob], Awaitable[None]]) -> None:
        """设置单条任务的异步执行器。"""
        self._runner = runner

    def set_on_change(
        self, callback: Callable[[str], Awaitable[None]] | None
    ) -> None:
        """注册队列状态变更后的可选回调（参数为受影响剧本 script_id）。"""
        self._on_change = callback

    async def enqueue(
        self,
        *,
        project_id: str,
        script_id: str,
        kind: GenerationKind,
        asset_id: str,
        label: str,
        source: GenerationSource,
        variant_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> GenerationJob:
        """入队一条生成任务；queued/running 同去重键时返回已有任务。"""
        async with self._lock:
            dedupe_key = f"{script_id}|{kind}|{asset_id}|{variant_id or ''}"
            existing = self._find_by_dedupe_key(
                dedupe_key, statuses=("queued", "running")
            )
            if existing is not None:
                return existing

            job = GenerationJob(
                id=new_job_id(),
                script_id=script_id,
                project_id=project_id,
                kind=kind,
                asset_id=asset_id,
                label=label,
                status="queued",
                source=source,
                variant_id=variant_id,
                payload=payload,
            )
            self._jobs[job.id] = job
            self._pending.append(job.id)
            self._done_events[job.id] = asyncio.Event()

        await self._notify_change(script_id)
        self._ensure_worker()
        return job

    def _find_by_dedupe_key(
        self,
        dedupe_key: str,
        statuses: tuple[GenerationStatus, ...],
    ) -> GenerationJob | None:
        """按去重键查找指定状态的任务。"""
        for job in self._jobs.values():
            if job.dedupe_key() == dedupe_key and job.status in statuses:
                return job
        return None

    def _ensure_worker(self) -> None:
        """确保后台工人协程已启动。"""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker_loop())

    async def _worker_loop(self) -> None:
        """串行消费 pending 队列，失败不阻塞后续任务。"""
        while True:
            job_id: str | None = None
            async with self._lock:
                if not self._pending:
                    break
                job_id = self._pending.popleft()
                job = self._jobs[job_id]
                job.status = "running"
                job.started_at = time.time()
                self._active_id = job_id

            await self._notify_change(job.script_id)

            job = self._jobs[job_id]
            try:
                if self._runner is not None:
                    await self._runner(job)
                job.status = "done"
                job.error = None
            except Exception as exc:
                job.status = "failed"
                job.error = str(exc)[:500]

            job.finished_at = time.time()

            async with self._lock:
                self._active_id = None
                self._recent.append(job_id)

            self._notify_waiter(job_id)
            await self._notify_change(job.script_id)

    def _notify_waiter(self, job_id: str) -> None:
        """通知 wait_until_done 等待者任务已终结。"""
        event = self._done_events.get(job_id)
        if event is not None:
            event.set()

    async def _notify_change(self, script_id: str) -> None:
        """触发可选状态变更回调。"""
        if self._on_change is not None:
            await self._on_change(script_id)

    async def wait_until_done(
        self,
        job_ids: list[str],
        timeout_sec: float | None = None,
    ) -> list[GenerationJob]:
        """等待指定任务进入 done 或 failed 状态后返回对应任务列表。"""
        results: list[GenerationJob] = []
        for job_id in job_ids:
            async with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    raise KeyError(f"unknown job: {job_id}")
                if job.status in ("done", "failed"):
                    results.append(job)
                    continue
                event = self._done_events.setdefault(job_id, asyncio.Event())

            if timeout_sec is not None:
                await asyncio.wait_for(event.wait(), timeout=timeout_sec)
            else:
                await event.wait()
            results.append(self._jobs[job_id])
        return results

    def snapshot_for_script(self, script_id: str) -> dict[str, Any]:
        """返回指定剧本的队列快照（WS/HTTP 公开结构）。"""
        active: dict[str, Any] | None = None
        queued: list[dict[str, Any]] = []
        recent: list[dict[str, Any]] = []
        project_id: str | None = None
        running_count = 0

        if self._active_id:
            active_job = self._jobs.get(self._active_id)
            if active_job and active_job.script_id == script_id:
                active = active_job.to_public_dict()
                project_id = active_job.project_id
                running_count = 1

        for job_id in self._pending:
            job = self._jobs.get(job_id)
            if job and job.script_id == script_id:
                queued.append(job.to_public_dict())
                if project_id is None:
                    project_id = job.project_id

        for job_id in reversed(self._recent):
            job = self._jobs.get(job_id)
            if job and job.script_id == script_id:
                recent.append(job.to_public_dict())
                if project_id is None:
                    project_id = job.project_id

        return {
            "type": "generation_queue_snapshot",
            "script_id": script_id,
            "project_id": project_id,
            "active": active,
            "queued": queued,
            "recent": recent,
            "counts": {
                "queued": len(queued),
                "running": running_count,
            },
        }


_queue_singleton: GenerationQueue | None = None


def get_generation_queue() -> GenerationQueue:
    """获取全局生成队列单例。"""
    global _queue_singleton
    if _queue_singleton is None:
        _queue_singleton = GenerationQueue()
    return _queue_singleton


def reset_generation_queue_for_tests() -> None:
    """重置全局单例，供测试隔离。"""
    global _queue_singleton
    if _queue_singleton is not None:
        worker = _queue_singleton._worker_task
        if worker is not None and not worker.done():
            worker.cancel()
        _queue_singleton = None
