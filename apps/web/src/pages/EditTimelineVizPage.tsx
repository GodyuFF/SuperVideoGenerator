/**
 * EditTimeline 独立可视化调试页（只读，与工作台解耦）。
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type { TrackClip } from "../edit/types";
import { AppShell } from "../components/layout/AppShell";
import { AppNavTrail } from "../components/layout/AppNavTrail";
import { AnalyzePanel } from "./editTimelineViz/AnalyzePanel";
import { ClipDetailPanel } from "./editTimelineViz/ClipDetailPanel";
import { JsonPanel } from "./editTimelineViz/JsonPanel";
import { TimelineVizPanel } from "./editTimelineViz/TimelineVizPanel";
import { ValidatePanel } from "./editTimelineViz/ValidatePanel";
import { formatMs } from "./editTimelineViz/formatMs";
import { useEditTimelineViz } from "./editTimelineViz/useEditTimelineViz";
import "./editTimelineViz/edit-timeline-viz.css";

interface EditTimelineVizPageProps {
  initialProjectId: string | null;
  initialScriptId: string | null;
  onBack: () => void;
  onNavigate: (projectId: string, scriptId: string) => void;
}

/** 统计各轨 clip 数量。 */
function countClips(timeline: NonNullable<ReturnType<typeof useEditTimelineViz>["timeline"]>) {
  const videoFromLayers = (timeline.video_layers ?? []).reduce(
    (n, layer) => n + (layer.clips?.length ?? 0),
    0,
  );
  const videoFlat = timeline.tracks?.video?.length ?? 0;
  return {
    videoLayers: timeline.video_layers?.length ?? 0,
    videoClips: videoFromLayers || videoFlat,
    audio: timeline.tracks?.audio?.length ?? 0,
    subtitle: timeline.tracks?.subtitle?.length ?? 0,
  };
}

/** EditTimeline 可视化主页面。 */
export function EditTimelineVizPage({
  initialProjectId,
  initialScriptId,
  onBack,
  onNavigate,
}: EditTimelineVizPageProps) {
  const [projectId, setProjectId] = useState(initialProjectId ?? "");
  const [scriptId, setScriptId] = useState(initialScriptId ?? "");
  const [loadedIds, setLoadedIds] = useState<{ project: string; script: string } | null>(
    initialProjectId && initialScriptId
      ? { project: initialProjectId, script: initialScriptId }
      : null,
  );
  const [selectedClip, setSelectedClip] = useState<TrackClip | null>(null);
  const [analyzeStart, setAnalyzeStart] = useState("");
  const [analyzeEnd, setAnalyzeEnd] = useState("");
  const [bottomTab, setBottomTab] = useState<"validate" | "analyze" | "json">("validate");

  const analyzeRange = useMemo(() => {
    const start = analyzeStart.trim() ? Number(analyzeStart) : undefined;
    const end = analyzeEnd.trim() ? Number(analyzeEnd) : undefined;
    if (start == null && end == null) return undefined;
    return {
      start_ms: Number.isFinite(start) ? start : undefined,
      end_ms: Number.isFinite(end) ? end : undefined,
    };
  }, [analyzeStart, analyzeEnd]);

  const { timeline, validate, analyze, loading, error, reload } = useEditTimelineViz(
    loadedIds?.project ?? "",
    loadedIds?.script ?? "",
    {
      enabled: Boolean(loadedIds?.project && loadedIds?.script),
      analyzeRange,
    },
  );

  useEffect(() => {
    if (initialProjectId) setProjectId(initialProjectId);
    if (initialScriptId) setScriptId(initialScriptId);
  }, [initialProjectId, initialScriptId]);

  const handleLoad = useCallback(() => {
    const p = projectId.trim();
    const s = scriptId.trim();
    if (!p || !s) return;
    setSelectedClip(null);
    setLoadedIds({ project: p, script: s });
    onNavigate(p, s);
  }, [projectId, scriptId, onNavigate]);

  const clipCounts = timeline ? countClips(timeline) : null;

  return (
    <AppShell
      pageClass="etviz-page"
      mainClass="etviz-main"
      title="EditTimeline 可视化"
      badge={<span className="status-badge muted-badge">EditTimeline 可视化</span>}
      lead={
        <button type="button" className="btn-secondary" onClick={onBack}>
          返回首页
        </button>
      }
      trail={<AppNavTrail />}
    >
      <p className="muted etviz-page-desc">只读调试 · 输入 project_id / script_id 查看剪辑时间轴</p>
      <section className="etviz-query card">
        <h2 className="etviz-section-title">查询</h2>
        <div className="etviz-query-row">
          <label className="etviz-field">
            <span>project_id</span>
            <input
              type="text"
              className="etviz-input mono"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              placeholder="proj_..."
            />
          </label>
          <label className="etviz-field">
            <span>script_id</span>
            <input
              type="text"
              className="etviz-input mono"
              value={scriptId}
              onChange={(e) => setScriptId(e.target.value)}
              placeholder="script_..."
            />
          </label>
          <button
            type="button"
            className="btn-primary"
            disabled={loading || !projectId.trim() || !scriptId.trim()}
            onClick={handleLoad}
          >
            加载
          </button>
          <button
            type="button"
            className="btn-secondary"
            disabled={loading || !loadedIds}
            onClick={() => void reload()}
          >
            刷新
          </button>
        </div>
        {loading ? <p className="muted">加载中…</p> : null}
        {error ? <p className="form-error">{error}</p> : null}
      </section>

      {timeline && loadedIds ? (
        <>
          <section className="etviz-summary card">
            <h2 className="etviz-section-title">概览</h2>
            <dl className="etviz-summary-dl">
              <div>
                <dt>timeline_id</dt>
                <dd className="mono">{timeline.timeline_id || "—"}</dd>
              </div>
              <div>
                <dt>plan_id</dt>
                <dd className="mono">{timeline.plan_id || "—"}</dd>
              </div>
              <div>
                <dt>duration</dt>
                <dd className="tabular-nums">
                  {formatMs(timeline.duration_ms)} ({timeline.duration_ms} ms)
                </dd>
              </div>
              <div>
                <dt>revision</dt>
                <dd>{timeline.revision ?? 0}</dd>
              </div>
              <div>
                <dt>user_edited</dt>
                <dd>{timeline.user_edited ? "是" : "否"}</dd>
              </div>
              <div>
                <dt>last_edited_by</dt>
                <dd>{timeline.last_edited_by || "—"}</dd>
              </div>
              <div>
                <dt>updated_at</dt>
                <dd className="mono">{timeline.updated_at || "—"}</dd>
              </div>
            </dl>
            {clipCounts ? (
              <p className="muted etviz-counts">
                视频层 {clipCounts.videoLayers} · 视频 clip {clipCounts.videoClips} · 音频{" "}
                {clipCounts.audio} · 字幕 {clipCounts.subtitle}
              </p>
            ) : null}
          </section>

          <section className="etviz-workspace">
            <div className="etviz-timeline-wrap card">
              <h2 className="etviz-section-title">时间轴</h2>
              <TimelineVizPanel
                timeline={timeline}
                selectedClipId={selectedClip?.id ? String(selectedClip.id) : null}
                onSelectClip={setSelectedClip}
              />
            </div>
            <ClipDetailPanel clip={selectedClip} onClose={() => setSelectedClip(null)} />
          </section>

          <section className="etviz-bottom card">
            <div className="etviz-tab-bar" role="tablist">
              {(
                [
                  ["validate", "校验"],
                  ["analyze", "分析"],
                  ["json", "原始 JSON"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={bottomTab === key}
                  className={`btn-secondary btn-sm${bottomTab === key ? " active" : ""}`}
                  onClick={() => setBottomTab(key)}
                >
                  {label}
                </button>
              ))}
            </div>
            {bottomTab === "validate" ? <ValidatePanel data={validate} /> : null}
            {bottomTab === "analyze" ? (
              <>
                <div className="etviz-analyze-filter">
                  <label className="etviz-field etviz-field--inline">
                    <span>start_ms</span>
                    <input
                      type="number"
                      className="etviz-input etviz-input--sm"
                      value={analyzeStart}
                      onChange={(e) => setAnalyzeStart(e.target.value)}
                      placeholder="可选"
                    />
                  </label>
                  <label className="etviz-field etviz-field--inline">
                    <span>end_ms</span>
                    <input
                      type="number"
                      className="etviz-input etviz-input--sm"
                      value={analyzeEnd}
                      onChange={(e) => setAnalyzeEnd(e.target.value)}
                      placeholder="可选"
                    />
                  </label>
                  <button
                    type="button"
                    className="btn-secondary btn-sm"
                    disabled={loading}
                    onClick={() => void reload()}
                  >
                    重新分析
                  </button>
                </div>
                <AnalyzePanel data={analyze} />
              </>
            ) : null}
            {bottomTab === "json" ? (
              <JsonPanel timeline={timeline} validate={validate} analyze={analyze} />
            ) : null}
          </section>
        </>
      ) : null}
    </AppShell>
  );
}
