import { useCallback, useEffect, useRef, useState } from "react";
import type { EditTimelineData } from "./types";

const API = "/api";

export function useEditTimeline(projectId: string, scriptId: string) {
  const [timeline, setTimeline] = useState<EditTimelineData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveAbortRef = useRef<AbortController | null>(null);
  /** Track latest revision from server responses so debounced saves always use current rev */
  const latestRevision = useRef<number>(0);
  /** Pending save data — stored separately so debounced saves don't capture stale closures */
  const pendingSave = useRef<EditTimelineData | null>(null);

  const fetchTimeline = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API}/projects/${projectId}/scripts/${scriptId}/edit-timeline`
      );
      if (res.status === 404) {
        setTimeline(null);
        return;
      }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `加载失败 ${res.status}`);
      }
      const data = (await res.json()) as EditTimelineData;
      setTimeline(data);
      latestRevision.current = data.revision ?? 0;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [projectId, scriptId]);

  useEffect(() => {
    void fetchTimeline();
  }, [fetchTimeline]);

  const saveTimeline = useCallback(
    async (next: EditTimelineData) => {
      // Cancel any in-flight save to avoid racing
      saveAbortRef.current?.abort();
      const controller = new AbortController();
      saveAbortRef.current = controller;

      setSaving(true);
      setError(null);
      try {
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
        };
        // Always use the latest known revision from the ref, not from the
        // closure-captured `next` object (which may be stale if the debounce
        // fired after another save already completed).
        if (latestRevision.current > 0 || next.revision != null) {
          headers["If-Match"] = String(latestRevision.current || (next.revision ?? 0));
        }
        const res = await fetch(
          `${API}/projects/${projectId}/scripts/${scriptId}/edit-timeline`,
          {
            method: "PATCH",
            headers,
            body: JSON.stringify({
              tracks: next.tracks,
              video_layers: next.video_layers,
              duration_ms: next.duration_ms,
            }),
            signal: controller.signal,
          }
        );
        if (res.status === 409) {
          // Revision conflict — re-fetch and retry once with fresh revision
          const body = await res.json().catch(() => ({}));
          const detail = (body.detail || "") as string;
          const match = /当前\s*(\d+)/.exec(detail);
          if (match) {
            latestRevision.current = parseInt(match[1], 10);
          }
          // Retry once with the updated revision
          const retryHeaders: Record<string, string> = {
            "Content-Type": "application/json",
          };
          retryHeaders["If-Match"] = String(latestRevision.current);
          const retryRes = await fetch(
            `${API}/projects/${projectId}/scripts/${scriptId}/edit-timeline`,
            {
              method: "PATCH",
              headers: retryHeaders,
              body: JSON.stringify({
                tracks: next.tracks,
                video_layers: next.video_layers,
                duration_ms: next.duration_ms,
              }),
            }
          );
          if (!retryRes.ok) {
            const retryBody = await retryRes.json().catch(() => ({}));
            throw new Error(retryBody.detail || `保存失败 ${retryRes.status}`);
          }
          const retryData = (await retryRes.json()) as EditTimelineData;
          setTimeline(retryData);
          latestRevision.current = retryData.revision ?? 0;
          return;
        }
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `保存失败 ${res.status}`);
        }
        const data = (await res.json()) as EditTimelineData;
        setTimeline(data);
        latestRevision.current = data.revision ?? 0;
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setSaving(false);
      }
    },
    [projectId, scriptId]
  );

  const scheduleSave = useCallback(
    (next: EditTimelineData) => {
      // Store the latest save data in a ref so the debounced callback
      // always sends the most recent data, not the closure-frozen copy.
      pendingSave.current = next;
      setTimeline(next);
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => {
        const toSave = pendingSave.current;
        if (toSave) {
          pendingSave.current = null;
          void saveTimeline(toSave);
        }
      }, 300);
    },
    [saveTimeline]
  );

  /** Force immediate save (used at drag-end to persist final state) */
  const flushSave = useCallback(() => {
    if (saveTimer.current) {
      clearTimeout(saveTimer.current);
      saveTimer.current = null;
    }
    const toSave = pendingSave.current;
    if (toSave) {
      pendingSave.current = null;
      void saveTimeline(toSave);
    }
  }, [saveTimeline]);

  /** 导出视频，支持进度回调 */
  const exportVideo = useCallback(
    async (onProgress?: (pct: number, msg: string) => void) => {
      // Step 1: Validate
      onProgress?.(5, "正在校验素材…");
      const validateRes = await fetch(
        `${API}/projects/${projectId}/scripts/${scriptId}/edit-timeline/validate`,
        { method: "POST" }
      );
      if (validateRes.ok) {
        const validation = (await validateRes.json()) as {
          ready?: boolean;
          validation?: { missing_items?: { reason?: string }[] };
        };
        if (validation.ready === false) {
          const reasons =
            validation.validation?.missing_items
              ?.map((m) => m.reason)
              .filter(Boolean)
              .slice(0, 3)
              .join("；") || "剪辑素材未齐备";
          throw new Error(`无法导出：${reasons}`);
        }
      }

      // Step 2: Submit export job
      onProgress?.(10, "正在提交导出任务…");
      const res = await fetch(
        `${API}/projects/${projectId}/scripts/${scriptId}/export`,
        { method: "POST" }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "导出失败");
      }
      const { job_id } = (await res.json()) as { job_id: string };

      // Step 3: Poll with progress
      for (let i = 0; i < 180; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const statusRes = await fetch(
          `${API}/projects/${projectId}/scripts/${scriptId}/export/${job_id}`
        );
        if (!statusRes.ok) continue;
        const job = (await statusRes.json()) as {
          status: string;
          result?: { url?: string; duration_ms?: number };
          error?: string;
          progress?: number;
        };
        if (job.status === "completed") {
          onProgress?.(100, "导出完成！");
          return job.result?.url ?? "";
        }
        if (job.status === "failed") throw new Error(job.error || "导出失败");
        // Show progress (linear estimate 10-95%)
        const pct = 10 + Math.min(85, (i / 60) * 85);
        onProgress?.(pct, "正在导出视频…");
      }
      throw new Error("导出超时（超过 3 分钟）");
    },
    [projectId, scriptId]
  );

  /** 导出纯画面+配音（skip_subtitles） */
  const exportVideoNoSubtitles = useCallback(
    async (onProgress?: (pct: number, msg: string) => void) => {
      onProgress?.(5, "正在校验素材…");
      const res = await fetch(
        `${API}/projects/${projectId}/scripts/${scriptId}/export?skip_subtitles=1`,
        { method: "POST" }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "导出失败");
      }
      const { job_id } = (await res.json()) as { job_id: string };
      for (let i = 0; i < 180; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const statusRes = await fetch(
          `${API}/projects/${projectId}/scripts/${scriptId}/export/${job_id}`
        );
        if (!statusRes.ok) continue;
        const job = (await statusRes.json()) as {
          status: string;
          result?: { url?: string };
          error?: string;
        };
        if (job.status === "completed") return job.result?.url ?? "";
        if (job.status === "failed") throw new Error(job.error || "导出失败");
        const pct = 10 + Math.min(85, (i / 60) * 85);
        onProgress?.(pct, "正在导出视频（无字幕）…");
      }
      throw new Error("导出超时");
    },
    [projectId, scriptId]
  );

  /** 下载导出的视频到本地 */
  const downloadExport = useCallback(
    async (url: string, filename?: string) => {
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || `export_${scriptId}_${Date.now()}.mp4`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    },
    [scriptId]
  );

  return {
    timeline,
    setTimeline,
    loading,
    error,
    saving,
    fetchTimeline,
    scheduleSave,
    saveTimeline,
    flushSave,
    exportVideo,
    exportVideoNoSubtitles,
    downloadExport,
  };
}