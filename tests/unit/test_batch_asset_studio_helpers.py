"""资源印样台纯逻辑对齐测试（缺媒体判定语义与前端一致）。

前端实现在 apps/web/src/utils/batchAssetStudio.ts；此处用等价规则锁契约，
避免看板 preview 文案被误判为已有媒体。
"""

from __future__ import annotations

import re


def _looks_like_media_url(raw: str | None) -> bool:
    """与前端 looksLikeMediaUrl 对齐的轻量判定。"""
    u = (raw or "").strip().replace("\\", "/")
    if not u:
        return False
    if u.startswith(("http://", "https://", "/api/", "file:")):
        return True
    if re.match(r"^[A-Za-z]:/", u):
        return True
    if re.match(r"^projects/[^/]+/scripts/[^/]+/assets/(media|exports)/", u):
        return True
    if re.search(r"\.(png|jpe?g|webp|gif|bmp|avif|svg|mp4|webm|mov|m4v)(\?|#|$)", u, re.I):
        return True
    if not re.search(r"[\s\u4e00-\u9fff]", u) and "." in u and "/" not in u:
        return True
    return False


def _looks_like_image_url(raw: str | None) -> bool:
    """与前端 looksLikeImageUrl 对齐：媒体 URL 且非视频扩展名。"""
    u = (raw or "").strip().replace("\\", "/")
    if not u or not _looks_like_media_url(u):
        return False
    if re.search(r"\.(mp4|webm|mov|m4v)(\?|#|$)", u, re.I):
        return False
    return True


def _looks_like_video_url(raw: str | None) -> bool:
    """与前端 looksLikeVideoUrl 对齐。"""
    u = (raw or "").strip().replace("\\", "/")
    if not u or not _looks_like_media_url(u):
        return False
    return bool(re.search(r"\.(mp4|webm|mov|m4v)(\?|#|$)", u, re.I))


def _pick_preview_url(item: dict) -> str:
    """与前端 pickBoardMediaPreviewUrl 对齐。"""
    candidates: list[str] = []
    preview_url = str(item.get("preview_url") or "").strip()
    if preview_url:
        candidates.append(preview_url)
    for key in ("images", "media", "videos"):
        for row in item.get(key) or []:
            if not isinstance(row, dict):
                continue
            for field in ("link", "url"):
                s = str(row.get(field) or "").strip()
                if s:
                    candidates.append(s)
    preview = str(item.get("preview") or "").strip()
    if preview:
        candidates.append(preview)
    for c in candidates:
        if _looks_like_media_url(c):
            return c
    return ""


def is_batch_studio_missing_media(item: dict) -> bool:
    """与前端 isBatchStudioMissingMedia 对齐。"""
    if _pick_preview_url(item):
        return False
    if str(item.get("primary_media_id") or "").strip():
        return False
    asset_type = str(item.get("type") or "").strip()
    if asset_type == "video_clip":
        for row in item.get("videos") or []:
            if isinstance(row, dict) and str(row.get("url") or "").strip():
                return False
        return True
    for row in item.get("images") or []:
        if isinstance(row, dict) and str(row.get("url") or "").strip():
            return False
    return True


def test_summary_preview_is_not_media() -> None:
    """中文摘要 preview 不得当作已有媒体。"""
    item = {
        "type": "character",
        "preview": "一位穿红衣的少女，站在雨巷里",
        "images": [],
    }
    assert is_batch_studio_missing_media(item) is True


def test_image_ext_is_image_not_video() -> None:
    """png 路径应判定为图片 URL，而非视频。"""
    url = "/api/projects/p/scripts/s/assets/media/a.png"
    assert _looks_like_media_url(url) is True
    assert _looks_like_image_url(url) is True
    assert _looks_like_video_url(url) is False


def test_mp4_is_video_not_image() -> None:
    """mp4 不得当作 <img> 预览源。"""
    url = "projects/p/scripts/s/assets/media/clip.mp4"
    assert _looks_like_media_url(url) is True
    assert _looks_like_image_url(url) is False
    assert _looks_like_video_url(url) is True


def test_cjk_name_is_not_media_url() -> None:
    """资产中文名不得当作预览 URL。"""
    assert _looks_like_media_url("午睡初醒") is False
    assert _looks_like_image_url("午睡初醒") is False


def test_preview_url_counts_as_ready() -> None:
    """preview_url 媒体路径应视为已有媒体。"""
    item = {
        "type": "frame",
        "preview": "分镜画面摘要",
        "preview_url": "/api/projects/p/scripts/s/assets/media/mid.png",
    }
    assert is_batch_studio_missing_media(item) is False


def test_video_clip_without_url_is_missing() -> None:
    """无视频 URL 的 video_clip 记为缺媒体。"""
    item = {"type": "video_clip", "videos": [], "preview": "动作特写"}
    assert is_batch_studio_missing_media(item) is True


def test_primary_media_id_counts_as_ready() -> None:
    """primary_media_id 视为已绑定媒体。"""
    item = {"type": "scene", "primary_media_id": "media_abc", "images": []}
    assert is_batch_studio_missing_media(item) is False


# --- 队列等待终态判定（与 generationQueueStatus.tickAssetQueueWait 对齐）---


def _job(
    job_id: str,
    asset_id: str,
    status: str,
    *,
    error: str | None = None,
) -> dict:
    return {
        "id": job_id,
        "asset_id": asset_id,
        "kind": "image",
        "label": asset_id,
        "status": status,
        "error": error,
    }


def _snapshot(
    *,
    active: dict | None = None,
    queued: list | None = None,
    recent: list | None = None,
) -> dict:
    return {
        "type": "generation_queue_snapshot",
        "script_id": "script_1",
        "active": active,
        "queued": queued or [],
        "recent": recent or [],
        "counts": {"queued": len(queued or []), "running": 1 if active else 0},
    }


def tick_asset_queue_wait(snapshot: dict, asset_id: str, prev: dict) -> dict:
    """与前端 tickAssetQueueWait 等价的纯逻辑。"""
    job_id = str(prev.get("jobId") or "").strip()
    saw_in_queue = bool(prev.get("sawInQueue"))

    def asset_active_or_queued() -> bool:
        active = snapshot.get("active")
        if active and active.get("asset_id") == asset_id:
            return True
        return any(j.get("asset_id") == asset_id for j in snapshot.get("queued") or [])

    def job_active_or_queued(jid: str) -> bool:
        active = snapshot.get("active")
        if active and active.get("id") == jid:
            return True
        return any(j.get("id") == jid for j in snapshot.get("queued") or [])

    def job_terminal(jid: str) -> str | None:
        for job in snapshot.get("recent") or []:
            if job.get("id") != jid:
                continue
            if job.get("status") in ("done", "failed"):
                return job["status"]
        return None

    def asset_recent_terminal() -> str | None:
        for job in snapshot.get("recent") or []:
            if job.get("asset_id") != asset_id:
                continue
            if job.get("status") in ("done", "failed"):
                return job["status"]
        return None

    if job_id:
        if job_active_or_queued(job_id):
            return {"state": {"sawInQueue": True, "jobId": job_id}, "complete": False}
        terminal = job_terminal(job_id)
        if terminal == "failed":
            return {
                "state": {"sawInQueue": True, "jobId": job_id},
                "complete": True,
                "outcome": "failed",
            }
        if terminal == "done":
            return {
                "state": {"sawInQueue": True, "jobId": job_id},
                "complete": True,
                "outcome": "done",
            }
        if asset_active_or_queued():
            saw_in_queue = True
        return {"state": {"sawInQueue": saw_in_queue, "jobId": job_id}, "complete": False}

    if asset_active_or_queued():
        return {"state": {"sawInQueue": True, "jobId": None}, "complete": False}
    if not saw_in_queue:
        return {"state": {"sawInQueue": False, "jobId": None}, "complete": False}
    terminal = asset_recent_terminal()
    if terminal in ("failed", "done"):
        return {
            "state": {"sawInQueue": saw_in_queue, "jobId": None},
            "complete": True,
            "outcome": terminal,
        }
    return {"state": {"sawInQueue": saw_in_queue, "jobId": None}, "complete": False}


def test_stale_recent_done_without_job_id_does_not_complete() -> None:
    """陈旧 recent done + 资产不在队列：未见过 queued/running 时不应判完成。"""
    snap = _snapshot(
        recent=[_job("old_job", "asset_a", "done")],
    )
    tick = tick_asset_queue_wait(snap, "asset_a", {"sawInQueue": False, "jobId": None})
    assert tick["complete"] is False


def test_job_id_waits_for_new_job_not_stale_asset_done() -> None:
    """有 job_id 时忽略 asset 级陈旧 done，直至该 job 进入 recent 终态。"""
    snap = _snapshot(
        recent=[_job("old_job", "asset_a", "done")],
    )
    tick = tick_asset_queue_wait(snap, "asset_a", {"sawInQueue": False, "jobId": "new_job"})
    assert tick["complete"] is False

    snap2 = _snapshot(recent=[_job("new_job", "asset_a", "done")])
    tick2 = tick_asset_queue_wait(snap2, "asset_a", tick["state"])
    assert tick2["complete"] is True
    assert tick2["outcome"] == "done"


def test_absent_from_queue_without_terminal_does_not_complete() -> None:
    """见过队列后离开但 recent 无终态：继续等待，不得默认 done。"""
    snap = _snapshot()
    tick = tick_asset_queue_wait(snap, "asset_a", {"sawInQueue": True, "jobId": None})
    assert tick["complete"] is False
