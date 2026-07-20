/** VideoPlan 拉取与用户编辑 Hook。 */

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  PatchVideoPlanShotBody,
  VideoPlanData,
  VideoPlanOp,
  VideoPlanSideEffects,
  VideoPlanShot,
} from "../types/videoPlan";

const API = "/api";

export interface UseVideoPlanOptions {
  /** 为 false 时不发起请求。 */
  enabled?: boolean;
}

/** 封装 video-plan GET/PATCH/ops/sync-from-tts。 */
export function useVideoPlan(
  projectId: string | null | undefined,
  scriptId: string | null | undefined,
  options: UseVideoPlanOptions = {},
) {
  const { enabled = true } = options;
  const [plan, setPlan] = useState<VideoPlanData | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const latestRevision = useRef(0);

  const fetchVideoPlan = useCallback(async (): Promise<VideoPlanData | null> => {
    if (!projectId || !scriptId || !enabled) return null;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API}/projects/${projectId}/scripts/${scriptId}/video-plan`,
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `加载失败 ${res.status}`);
      }
      const data = (await res.json()) as VideoPlanData;
      setPlan(data);
      latestRevision.current = data.detail_revision ?? 0;
      return data;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    } finally {
      setLoading(false);
    }
  }, [projectId, scriptId, enabled]);

  useEffect(() => {
    if (enabled && projectId && scriptId) {
      void fetchVideoPlan();
    }
  }, [enabled, projectId, scriptId, fetchVideoPlan]);

  const getShotById = useCallback(
    (shotId: string): VideoPlanShot | undefined =>
      plan?.shots?.find((s) => s.id === shotId),
    [plan],
  );

  const patchShot = useCallback(
    async (
      shotId: string,
      body: PatchVideoPlanShotBody,
    ): Promise<{ data: VideoPlanData; sideEffects?: VideoPlanSideEffects }> => {
      if (!projectId || !scriptId) throw new Error("缺少 projectId 或 scriptId");
      setSaving(true);
      setError(null);
      try {
        const res = await fetch(
          `${API}/projects/${projectId}/scripts/${scriptId}/video-plan/shots/${shotId}`,
          {
            method: "PATCH",
            headers: {
              "Content-Type": "application/json",
              "If-Match": String(latestRevision.current),
            },
            body: JSON.stringify(body),
          },
        );
        if (res.status === 409) {
          await fetchVideoPlan();
          throw new Error("版本冲突，已刷新数据，请重试");
        }
        if (!res.ok) {
          const errBody = await res.json().catch(() => ({}));
          throw new Error(errBody.detail || `保存失败 ${res.status}`);
        }
        const data = (await res.json()) as VideoPlanData;
        setPlan(data);
        latestRevision.current = data.detail_revision ?? latestRevision.current;
        return { data, sideEffects: data.side_effects };
      } finally {
        setSaving(false);
      }
    },
    [projectId, scriptId, fetchVideoPlan],
  );

  const applyOps = useCallback(
    async (
      ops: VideoPlanOp[],
    ): Promise<{ data: VideoPlanData; sideEffects?: VideoPlanSideEffects }> => {
      if (!projectId || !scriptId) throw new Error("缺少 projectId 或 scriptId");
      setSaving(true);
      setError(null);
      try {
        const res = await fetch(
          `${API}/projects/${projectId}/scripts/${scriptId}/video-plan/ops`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "If-Match": String(latestRevision.current),
            },
            body: JSON.stringify({ ops, expected_revision: latestRevision.current }),
          },
        );
        if (res.status === 409) {
          await fetchVideoPlan();
          throw new Error("版本冲突，已刷新数据，请重试");
        }
        if (!res.ok) {
          const errBody = await res.json().catch(() => ({}));
          throw new Error(errBody.detail || `操作失败 ${res.status}`);
        }
        const data = (await res.json()) as VideoPlanData;
        setPlan(data);
        latestRevision.current = data.detail_revision ?? latestRevision.current;
        return { data, sideEffects: data.side_effects };
      } finally {
        setSaving(false);
      }
    },
    [projectId, scriptId, fetchVideoPlan],
  );

  const syncFromTts = useCallback(async (): Promise<Record<string, unknown>> => {
    if (!projectId || !scriptId) throw new Error("缺少 projectId 或 scriptId");
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(
        `${API}/projects/${projectId}/scripts/${scriptId}/video-plan/sync-from-tts`,
        { method: "POST" },
      );
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody.detail || `同步失败 ${res.status}`);
      }
      const result = await res.json();
      await fetchVideoPlan();
      return result as Record<string, unknown>;
    } finally {
      setSaving(false);
    }
  }, [projectId, scriptId, fetchVideoPlan]);

  /** 分析/应用音画时长协调。 */
  const analyzeAvSync = useCallback(
    async (opts?: {
      mode?: "analyze_only" | "hybrid" | "auto_only";
      shotIds?: string[];
    }): Promise<Record<string, unknown>> => {
      if (!projectId || !scriptId) throw new Error("缺少 projectId 或 scriptId");
      setSaving(true);
      setError(null);
      try {
        const res = await fetch(
          `${API}/projects/${projectId}/scripts/${scriptId}/video-plan/av-sync`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              mode: opts?.mode ?? "analyze_only",
              shot_ids: opts?.shotIds,
            }),
          },
        );
        if (!res.ok) {
          const errBody = await res.json().catch(() => ({}));
          throw new Error(errBody.detail || `音画分析失败 ${res.status}`);
        }
        const result = await res.json();
        if ((opts?.mode ?? "analyze_only") !== "analyze_only") {
          await fetchVideoPlan();
        }
        return result as Record<string, unknown>;
      } finally {
        setSaving(false);
      }
    },
    [projectId, scriptId, fetchVideoPlan],
  );

  /** 应用单镜音画协调方案。 */
  const applyAvSyncAction = useCallback(
    async (
      shotId: string,
      action: Record<string, unknown>,
    ): Promise<Record<string, unknown>> => {
      if (!projectId || !scriptId) throw new Error("缺少 projectId 或 scriptId");
      setSaving(true);
      setError(null);
      try {
        const res = await fetch(
          `${API}/projects/${projectId}/scripts/${scriptId}/video-plan/shots/${shotId}/av-sync/apply`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action }),
          },
        );
        if (!res.ok) {
          const errBody = await res.json().catch(() => ({}));
          throw new Error(errBody.detail || `应用方案失败 ${res.status}`);
        }
        const result = await res.json();
        await fetchVideoPlan();
        return result as Record<string, unknown>;
      } finally {
        setSaving(false);
      }
    },
    [projectId, scriptId, fetchVideoPlan],
  );

  return {
    plan,
    loading,
    saving,
    error,
    detailRevision: plan?.detail_revision ?? 0,
    editable: plan?.editable ?? false,
    fetchVideoPlan,
    getShotById,
    patchShot,
    applyOps,
    syncFromTts,
    analyzeAvSync,
    applyAvSyncAction,
  };
}
