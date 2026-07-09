/** 剪辑 Tab 简易视图：OpenCut 预览、播放、导出与打开专业剪辑弹窗。 */

import { Component, type ErrorInfo, type ReactNode, useEffect, useRef, useState } from "react";
import { useAppTranslation } from "../i18n/useAppTranslation";
import { fetchEditCapabilities } from "./adapter/capabilitiesAdapter";
import { bindEditWsEvents, unbindEditWsEvents } from "./editWsBinding";
import { prefetchClassicStudio } from "./classicPrefetch";
import {
  OpenCutPreviewPane,
  type OpenCutPreviewPaneHandle,
} from "./OpenCutPreviewPane";
import type { EditCapabilities } from "../edit/types";
import type { EditTimelineApi } from "../edit/useEditTimeline";

interface EditTabSimpleViewProps {
  projectId: string;
  scriptId: string;
  timelineApi: EditTimelineApi;
  onStudioOpenChange: (open: boolean) => void;
  /** 专业剪辑弹窗是否已打开（与 Tab 预览互斥 EditorCore）。 */
  studioOpen?: boolean;
}

/** 捕获剪辑 Tab 运行时错误，避免整页白屏。 */
class EditTabErrorBoundary extends Component<
  { children: ReactNode; onRetry: () => void },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("EditTabSimpleView error:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <EditTabErrorFallback
          error={this.state.error}
          onRetry={() => {
            this.setState({ error: null });
            this.props.onRetry();
          }}
        />
      );
    }
    return this.props.children;
  }
}

/** 错误边界回退 UI（需 Hook 翻译）。 */
function EditTabErrorFallback({
  error,
  onRetry,
}: {
  error: Error;
  onRetry: () => void;
}) {
  const { t } = useAppTranslation(["editor", "common"]);
  return (
    <div className="edit-tab-simple empty">
      <p className="board-error">{t("editor:previewLoadFailed", { error: error.message })}</p>
      <button
        type="button"
        className="btn-secondary btn-sm"
        onClick={onRetry}
      >
        {t("common:actions.retry")}
      </button>
    </div>
  );
}

function formatMs(ms: number): string {
  const sec = Math.floor(ms / 1000);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  const frac = Math.floor((ms % 1000) / 100);
  return `${m}:${s.toString().padStart(2, "0")}.${frac}`;
}

/** 剪辑 Tab 简易预览与导出入口。 */
function EditTabSimpleViewInner({
  projectId,
  scriptId,
  timelineApi,
  onStudioOpenChange,
  studioOpen = false,
}: EditTabSimpleViewProps) {
  const { t } = useAppTranslation(["editor", "common"]);
  const previewRef = useRef<OpenCutPreviewPaneHandle>(null);
  const [playheadMs, setPlayheadMs] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [capabilities, setCapabilities] = useState<EditCapabilities | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportingNle, setExportingNle] = useState(false);
  const [exportMsg, setExportMsg] = useState("");
  const [exportProgress, setExportProgress] = useState<{ pct: number; msg: string } | null>(null);
  const [exportUrl, setExportUrl] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const prevStudioOpenRef = useRef(studioOpen);

  const {
    timeline,
    loading,
    error,
    flushSave,
    exportVideo,
    exportVideoNoSubtitles,
    exportNleProject,
    downloadExport,
    fetchTimeline,
  } = timelineApi;

  useEffect(() => {
    void fetchEditCapabilities().then(setCapabilities);
    void prefetchClassicStudio();
  }, []);

  useEffect(() => {
    bindEditWsEvents(projectId, scriptId);
    const onReload = (ev: Event) => {
      const detail = (ev as CustomEvent).detail as { scriptId?: string };
      if (detail?.scriptId && detail.scriptId !== scriptId) return;
      void fetchTimeline().then(() => setRefreshKey((k) => k + 1));
    };
    window.addEventListener("svg:edit-timeline-reloaded", onReload);
    return () => {
      unbindEditWsEvents(projectId, scriptId);
      window.removeEventListener("svg:edit-timeline-reloaded", onReload);
    };
  }, [projectId, scriptId, fetchTimeline]);

  /** 弹窗关闭后 soft-reload OpenCut 预览，与 Classic 编辑结果对齐。 */
  useEffect(() => {
    if (prevStudioOpenRef.current && !studioOpen && timeline) {
      void (async () => {
        const bridge = await import("./classicAgentBridge");
        await bridge.reloadClassicFromApi(projectId, scriptId, timeline);
        setRefreshKey((k) => k + 1);
      })();
    }
    prevStudioOpenRef.current = studioOpen;
  }, [studioOpen, projectId, scriptId, timeline]);

  const ffmpegAvailable = capabilities?.ffmpeg_available !== false;
  const exportEnabled = capabilities?.export_enabled !== false;
  const nleExportEnabled = capabilities?.nle_export_enabled !== false;
  const ffmpegHint = t("editor:ffmpegHint");
  const noTimelineHint = error || t("editor:noTimelineHint");

  async function handleExport(noSubtitles = false) {
    if (!timeline) return;
    setExporting(true);
    setExportMsg("");
    setExportProgress(null);
    setExportUrl(null);
    try {
      await flushSave(timeline);
      const url = noSubtitles
        ? await exportVideoNoSubtitles((pct, msg) => setExportProgress({ pct, msg }))
        : await exportVideo((pct, msg) => setExportProgress({ pct, msg }));
      setExportUrl(url);
      setExportMsg(url ? t("editor:exportDone") : t("editor:exportDoneShort"));
    } catch (e) {
      setExportMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setExporting(false);
      setExportProgress(null);
    }
  }

  async function handleExportNle() {
    if (!timeline) return;
    setExportingNle(true);
    setExportMsg("");
    setExportProgress(null);
    setExportUrl(null);
    try {
      await flushSave(timeline);
      const url = await exportNleProject((pct, msg) => setExportProgress({ pct, msg }));
      setExportUrl(url);
      setExportMsg(url ? t("editor:exportNleDone") : t("editor:exportNleDoneShort"));
    } catch (e) {
      setExportMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setExportingNle(false);
      setExportProgress(null);
    }
  }

  async function handleDownload() {
    if (!exportUrl) return;
    const isZip = exportUrl.includes("nle_premiere_");
    await downloadExport(
      exportUrl,
      isZip ? `nle_premiere_${scriptId}_${Date.now()}.zip` : undefined,
    );
  }

  const handlePlaybackChange = (ms: number, isPlaying: boolean) => {
    setPlayheadMs(ms);
    setPlaying(isPlaying);
  };

  if (loading && !timeline) {
    return <p className="muted">{t("editor:loadingEditPreview")}</p>;
  }

  const durationMs = timeline?.duration_ms || 0;
  const hasTimeline = Boolean(timeline);

  return (
    <div className="edit-cinema">
      <header className="edit-cinema-header">
        <div className="edit-cinema-group svf-studio-chrome-group">
          <span className="edit-cinema-group-label">{t("editor:cinemaMonitor")}</span>
          {hasTimeline ? (
            <span className="edit-cinema-timecode">
              {formatMs(playheadMs)} / {formatMs(durationMs)}
            </span>
          ) : (
            <span className="muted edit-cinema-timecode">{noTimelineHint}</span>
          )}
          <button
            type="button"
            className="btn-secondary btn-sm"
            disabled={!hasTimeline || studioOpen}
            onClick={() => {
              const api = previewRef.current;
              if (!api) return;
              void (async () => {
                if (playing) await api.pause();
                else await api.play();
              })();
            }}
          >
            {playing ? t("common:actions.pause") : t("common:actions.play")}
          </button>
          <button
            type="button"
            className="btn-secondary btn-sm"
            disabled={!hasTimeline || studioOpen}
            onClick={() => {
              const api = previewRef.current;
              if (!api) return;
              void (async () => {
                await api.pause();
                await api.seek(0);
              })();
            }}
          >
            {t("common:actions.stop")}
          </button>
        </div>

        <span className="edit-cinema-divider" aria-hidden />

        <div className="edit-cinema-group svf-studio-chrome-group">
          <span className="edit-cinema-group-label">{t("editor:cinemaExport")}</span>
          <button
            type="button"
            className="btn-primary btn-sm"
            disabled={!hasTimeline || exporting || !exportEnabled}
            title={!exportEnabled ? ffmpegHint : undefined}
            onClick={() => void handleExport(false)}
          >
            {exporting ? t("editor:exporting") : t("editor:exportMp4")}
          </button>
          <button
            type="button"
            className="btn-secondary btn-sm"
            disabled={!hasTimeline || exporting || !exportEnabled}
            onClick={() => void handleExport(true)}
          >
            {t("editor:exportNoSubs")}
          </button>
          <button
            type="button"
            className="btn-secondary btn-sm"
            disabled={!hasTimeline || exporting || exportingNle || !nleExportEnabled}
            title={t("editor:exportNlePremiereHint")}
            onClick={() => void handleExportNle()}
          >
            {exportingNle ? t("editor:exportNleExporting") : t("editor:exportNlePremiere")}
          </button>
          {exportUrl && (
            <button type="button" className="btn-secondary btn-sm" onClick={() => void handleDownload()}>
              {t("common:actions.download")}
            </button>
          )}
        </div>

        <span className="edit-cinema-divider" aria-hidden />

        <div className="edit-cinema-group svf-studio-chrome-group">
          <span className="edit-cinema-group-label">{t("editor:cinemaStudio")}</span>
          <button
            type="button"
            className="btn-primary btn-sm"
            disabled={!hasTimeline}
            title={!hasTimeline ? noTimelineHint : t("editor:openStudioTitle")}
            onMouseEnter={() => prefetchClassicStudio()}
            onClick={() => onStudioOpenChange(true)}
          >
            {t("editor:editStudio")}
          </button>
          {!hasTimeline && (
            <button type="button" className="btn-secondary btn-sm" onClick={() => void fetchTimeline()}>
              {t("common:actions.retry")}
            </button>
          )}
        </div>
      </header>

      <div className="edit-cinema-viewport">
        <div className="edit-cinema-viewport-frame">
          {hasTimeline ? (
            <OpenCutPreviewPane
              key={`${projectId}-${scriptId}-${refreshKey}`}
              ref={previewRef}
              projectId={projectId}
              scriptId={scriptId}
              timeline={timeline!}
              paused={studioOpen}
              onPlaybackChange={handlePlaybackChange}
            />
          ) : (
            <div className="edit-cinema-preview-state muted">
              <p>{t("editor:previewReadyHint")}</p>
            </div>
          )}
        </div>
      </div>

      {(error && hasTimeline) || exportMsg || exportProgress || !ffmpegAvailable ? (
        <div className="edit-cinema-footer edit-cinema-status">
          {error && hasTimeline && <p className="board-error">{error}</p>}
          {exportMsg && <p className="muted">{exportMsg}</p>}
          {exportProgress && (
            <div className="edit-studio-export-progress">
              <div
                className="edit-studio-export-progress-bar"
                style={{ width: `${exportProgress.pct}%` }}
              />
              <span className="edit-studio-export-progress-text">
                {exportProgress.msg} ({Math.round(exportProgress.pct)}%)
              </span>
            </div>
          )}
          {!ffmpegAvailable && <p className="board-error">{ffmpegHint}</p>}
        </div>
      ) : null}
    </div>
  );
}

/** 带错误边界的剪辑 Tab 入口。 */
export function EditTabSimpleView(props: EditTabSimpleViewProps) {
  const [retryKey, setRetryKey] = useState(0);
  return (
    <EditTabErrorBoundary onRetry={() => setRetryKey((k) => k + 1)}>
      <EditTabSimpleViewInner key={retryKey} {...props} />
    </EditTabErrorBoundary>
  );
}
