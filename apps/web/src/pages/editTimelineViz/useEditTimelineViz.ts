/** 只读拉取 EditTimeline + validate + analyze（并行请求）。 */

import { useCallback, useEffect, useState } from "react";
import type { EditTimelineData } from "../../edit/types";
import type {
  AnalyzeRangeFilter,
  EditTimelineAnalyzeResponse,
  EditTimelineValidateResponse,
} from "./types";

const API = "/api";

export interface UseEditTimelineVizOptions {
  /** 为 false 时不发起请求。 */
  enabled?: boolean;
  /** analyze 时间窗（可选）。 */
  analyzeRange?: AnalyzeRangeFilter;
}

/** 封装 edit-timeline GET / validate / analyze 三接口并行加载。 */
export function useEditTimelineViz(
  projectId: string,
  scriptId: string,
  options: UseEditTimelineVizOptions = {},
) {
  const { enabled = true, analyzeRange } = options;
  const [timeline, setTimeline] = useState<EditTimelineData | null>(null);
  const [validate, setValidate] = useState<EditTimelineValidateResponse | null>(null);
  const [analyze, setAnalyze] = useState<EditTimelineAnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!projectId.trim() || !scriptId.trim()) {
      setError("请填写 project_id 与 script_id");
      return;
    }
    setLoading(true);
    setError(null);
    const base = `${API}/projects/${encodeURIComponent(projectId)}/scripts/${encodeURIComponent(scriptId)}/edit-timeline`;
    const analyzeBody: Record<string, unknown> = { include_analysis: true };
    if (analyzeRange?.start_ms != null) analyzeBody.start_ms = analyzeRange.start_ms;
    if (analyzeRange?.end_ms != null) analyzeBody.end_ms = analyzeRange.end_ms;

    try {
      const [timelineRes, validateRes, analyzeRes] = await Promise.all([
        fetch(base),
        fetch(`${base}/validate`, { method: "POST" }),
        fetch(`${base}/analyze`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(analyzeBody),
        }),
      ]);

      if (timelineRes.status === 404) {
        throw new Error("剧本不存在或 project_id / script_id 不匹配");
      }
      if (!timelineRes.ok) {
        const body = await timelineRes.json().catch(() => ({}));
        throw new Error(String(body.detail || `加载时间轴失败 ${timelineRes.status}`));
      }

      const timelineData = (await timelineRes.json()) as EditTimelineData;
      setTimeline(timelineData);

      if (validateRes.ok) {
        setValidate((await validateRes.json()) as EditTimelineValidateResponse);
      } else {
        setValidate(null);
      }

      if (analyzeRes.ok) {
        setAnalyze((await analyzeRes.json()) as EditTimelineAnalyzeResponse);
      } else {
        setAnalyze(null);
      }
    } catch (e) {
      setTimeline(null);
      setValidate(null);
      setAnalyze(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [projectId, scriptId, analyzeRange?.start_ms, analyzeRange?.end_ms]);

  useEffect(() => {
    if (enabled && projectId.trim() && scriptId.trim()) {
      void reload();
    }
    // analyzeRange 仅在手点「重新分析」时生效，避免输入框每次变更都触发请求
  }, [enabled, projectId, scriptId]); // eslint-disable-line react-hooks/exhaustive-deps

  return { timeline, validate, analyze, loading, error, reload };
}
