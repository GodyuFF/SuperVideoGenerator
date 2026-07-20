/** 剪辑 Tab 简易视图：OpenCut 预览、播放与打开专业剪辑弹窗（成片导出仅在剪辑器内）。 */

import { Component, type ErrorInfo, type ReactNode, useEffect, useRef, useState } from "react";
import { useAppTranslation } from "../i18n/useAppTranslation";
import { fetchEditCapabilities } from "./adapter/capabilitiesAdapter";
import { bindEditWsEvents, unbindEditWsEvents } from "./editWsBinding";
import { prefetchClassicStudio } from "./classicPrefetch";
import { reloadClassicFromApi } from "./classicAgentBridge";
import { svfProjectKey } from "./adapter/svfProjectAdapter";
import {
  getSvfProjectMediaCache,
  getMediaHydrationIssues,
  listMediaHydrationMessageKeys,
} from "./adapter/SvfMediaBridge";
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

/** 将毫秒格式化为监视器时间码（M:SS.xx）。 */
function formatMonitorTimecode(ms: number): string {
  const clamped = Math.max(0, ms);
  const totalSec = clamped / 1000;
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${s.toFixed(2).padStart(5, "0")}`;
}

/** 剪辑 Tab 简易预览；支持 Tab 内浏览器导出与实时监视器时码。 */
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
  const [durationMs, setDurationMs] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [exportHost, setExportHost] = useState<HTMLDivElement | null>(null);
  const [capabilities, setCapabilities] = useState<EditCapabilities | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const {
    timeline,
    loading,
    error,
    fetchTimeline,
    saveTimeline,
  } = timelineApi;

  const mediaHydrationBlocked = (() => {
    const key = svfProjectKey(projectId, scriptId);
    const issues = getMediaHydrationIssues(getSvfProjectMediaCache(key));
    return listMediaHydrationMessageKeys(issues).length > 0;
  })();

  useEffect(() => {
    void fetchEditCapabilities().then(setCapabilities);
    void prefetchClassicStudio();
  }, []);

  useEffect(() => {
    bindEditWsEvents(projectId, scriptId);
    const onReload = (ev: Event) => {
      const detail = (ev as CustomEvent).detail as { scriptId?: string };
      if (detail?.scriptId && detail.scriptId !== scriptId) return;
      void (async () => {
        await fetchTimeline({ silent: true });
        await reloadClassicFromApi(projectId, scriptId);
        setRefreshKey((k) => k + 1);
      })();
    };
    window.addEventListener("svg:edit-timeline-reloaded", onReload);
    return () => {
      unbindEditWsEvents(projectId, scriptId);
      window.removeEventListener("svg:edit-timeline-reloaded", onReload);
    };
  }, [projectId, scriptId, fetchTimeline]);

  const classicExportEnabled = capabilities?.classic_export_enabled !== false;
  const noTimelineHint = error || t("editor:noTimelineHint");
  const hasTimeline = Boolean(timeline && !loading);
  const displayDurationMs = durationMs > 0 ? durationMs : (timeline?.duration_ms ?? 0);

  const handlePlaybackChange = (state: {
    playheadMs: number;
    durationMs: number;
    playing: boolean;
  }) => {
    setPlayheadMs(state.playheadMs);
    setDurationMs(state.durationMs);
    setPlaying(state.playing);
  };

  return (
    <div className="edit-cinema">
      <header className="edit-cinema-header">
        <div className="edit-cinema-toolbar-left">
          {hasTimeline ? (
            <span className="edit-cinema-timecode">
              {formatMonitorTimecode(playheadMs)} / {formatMonitorTimecode(displayDurationMs)}
            </span>
          ) : (
            <span className="muted edit-cinema-timecode">{noTimelineHint}</span>
          )}
          <div className="edit-cinema-transport">
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
        </div>

        <div className="edit-cinema-toolbar-right">
          <button
            type="button"
            className="btn-secondary btn-sm"
            disabled={loading}
            title={t("editor:reloadTimelineTitle")}
            onClick={() => {
              void (async () => {
                await fetchTimeline();
                setRefreshKey((k) => k + 1);
              })();
            }}
          >
            {loading ? t("common:actions.loading") : t("editor:reloadTimeline")}
          </button>
          {classicExportEnabled ? (
            <div
              ref={setExportHost}
              className="edit-cinema-export-slot"
              aria-label={t("editor:tabExportSlot")}
            />
          ) : (
            <span className="muted text-sm">{t("editor:exportViaEditorShort")}</span>
          )}
          <button
            type="button"
            className="btn-secondary btn-sm edit-cinema-studio-btn"
            disabled={!hasTimeline || mediaHydrationBlocked}
            title={
              mediaHydrationBlocked
                ? t("editor:mediaHydrationBlockedExport")
                : !hasTimeline
                  ? noTimelineHint
                  : t("editor:openStudioTitle")
            }
            onMouseEnter={() => prefetchClassicStudio()}
            onClick={() => onStudioOpenChange(true)}
          >
            {t("editor:editStudio")}
          </button>
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
              exportHost={exportHost}
              onPlaybackChange={handlePlaybackChange}
              onSaveTimeline={saveTimeline}
            />
          ) : (
            <div className="edit-cinema-preview-state muted">
              <p>{t("editor:previewReadyHint")}</p>
            </div>
          )}
        </div>
      </div>

      {error && hasTimeline && (
        <div className="edit-cinema-footer edit-cinema-status">
          <p className="board-error">{error}</p>
        </div>
      )}
    </div>
  );
}

/** 剪辑 Tab 入口（含错误边界）。 */
export function EditTabSimpleView(props: EditTabSimpleViewProps) {
  const [retryKey, setRetryKey] = useState(0);
  return (
    <EditTabErrorBoundary onRetry={() => setRetryKey((k) => k + 1)} key={retryKey}>
      <EditTabSimpleViewInner {...props} />
    </EditTabErrorBoundary>
  );
}
