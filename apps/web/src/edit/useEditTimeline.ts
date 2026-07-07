import { useCallback, useEffect, useRef, useState } from "react";
import type { EditTimelineData } from "./types";

const API = "/api";

export function useEditTimeline(projectId: string, scriptId: string) {
  const [timeline, setTimeline] = useState<EditTimelineData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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
      setSaving(true);
      setError(null);
      try {
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
        };
        if (next.revision != null) {
          headers["If-Match"] = String(next.revision);
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
          }
        );
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `保存失败 ${res.status}`);
        }
        const data = (await res.json()) as EditTimelineData;
        setTimeline(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setSaving(false);
      }
    },
    [projectId, scriptId]
  );

  const scheduleSave = useCallback(
    (next: EditTimelineData) => {
      setTimeline(next);
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => {
        void saveTimeline(next);
      }, 500);
    },
    [saveTimeline]
  );

  const exportVideo = useCallback(async () => {
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

    const res = await fetch(
      `${API}/projects/${projectId}/scripts/${scriptId}/export`,
      { method: "POST" }
    );
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "导出失败");
    }
    const { job_id } = (await res.json()) as { job_id: string };
    for (let i = 0; i < 120; i++) {
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
    }
    throw new Error("导出超时");
  }, [projectId, scriptId]);

  return {
    timeline,
    setTimeline,
    loading,
    error,
    saving,
    fetchTimeline,
    scheduleSave,
    saveTimeline,
    exportVideo,
  };
}
