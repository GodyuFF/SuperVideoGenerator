"""剪辑导出异步任务（内存 job 表）。"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass
class ExportJob:
    id: str
    project_id: str
    script_id: str
    status: str = "pending"
    progress: float = 0.0
    message: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    created_at: str = ""
    updated_at: str = ""


_lock = threading.Lock()
_jobs: dict[str, ExportJob] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_export_job(project_id: str, script_id: str) -> ExportJob:
    job = ExportJob(
        id=f"exp_{uuid.uuid4().hex[:12]}",
        project_id=project_id,
        script_id=script_id,
        created_at=_now_iso(),
        updated_at=_now_iso(),
    )
    with _lock:
        _jobs[job.id] = job
    return job


def get_export_job(job_id: str) -> ExportJob | None:
    with _lock:
        return _jobs.get(job_id)


def update_export_job(
    job_id: str,
    *,
    status: str | None = None,
    progress: float | None = None,
    message: str | None = None,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> ExportJob | None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        if status is not None:
            job.status = status
        if progress is not None:
            job.progress = progress
        if message is not None:
            job.message = message
        if result is not None:
            job.result = result
        if error is not None:
            job.error = error
        job.updated_at = _now_iso()
        return job


def run_export_job(job_id: str, worker: Callable[[ExportJob], dict[str, Any]]) -> None:
    job = get_export_job(job_id)
    if job is None:
        return
    update_export_job(job_id, status="running", progress=0.05, message="准备导出")
    try:
        result = worker(job)
        update_export_job(
            job_id,
            status="completed",
            progress=1.0,
            message="导出完成",
            result=result,
        )
    except Exception as exc:
        update_export_job(
            job_id,
            status="failed",
            progress=1.0,
            message="导出失败",
            error=str(exc),
        )


def job_to_dict(job: ExportJob) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "project_id": job.project_id,
        "script_id": job.script_id,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }
