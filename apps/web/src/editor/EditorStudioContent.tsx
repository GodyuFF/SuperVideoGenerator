/** 专业剪辑核心 UI（弹窗与独立页共用）。 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useAppTranslation } from "../i18n/useAppTranslation";
import { fetchEditCapabilities } from "./adapter/capabilitiesAdapter";
import { prefetchClassicEditor, getClassicEditorModule } from "./classicPrefetch";
import { getClassicBridgeTimeline } from "./classicAgentBridge";
import { openEditorStudioInNewTab } from "./editorStudioUrls";
import { ThemeToggle } from "../components/theme/ThemeToggle";
import { LocaleSwitcher } from "../i18n/LocaleSwitcher";
import type { EditCapabilities, EditTimelineData } from "../edit/types";
import type { EditTimelineApi } from "../edit/useEditTimeline";
import type { ClassicLoadStage } from "./opencut/SvfClassicEditor";

interface EditorStudioContentProps {
  projectId: string;
  scriptId: string;
  timelineApi: EditTimelineApi;
  onClose: (saved: boolean) => void;
  /** 顶栏是否显示「新标签页打开」。 */
  showOpenInNewTab?: boolean;
  /** 外层容器 class（page / modal 布局差异）。 */
  shellClassName?: string;
}

/** OpenCut Classic 剪辑工作室内容区（顶栏 + 编辑器）。 */
export function EditorStudioContent({
  projectId,
  scriptId,
  timelineApi,
  onClose,
  showOpenInNewTab = false,
  shellClassName = "",
}: EditorStudioContentProps) {
  const { t } = useAppTranslation(["editor", "common", "nav"]);
  const [capabilities, setCapabilities] = useState<EditCapabilities | null>(null);
  const [ClassicEditor, setClassicEditor] = useState<{
    SvfClassicEditor: typeof import("./opencut/SvfClassicEditor").SvfClassicEditor;
  } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadStage, setLoadStage] = useState<ClassicLoadStage>("module");

  const { timeline, flushSave, saveTimeline, exportVideo, exportNleProject, saving, loading, error, fetchTimeline } =
    timelineApi;
  const [exporting, setExporting] = useState(false);
  const [exportingNle, setExportingNle] = useState(false);
  const [exportMsg, setExportMsg] = useState("");

  /** 打开时冻结 timeline 快照，避免保存后 prop 变化触发 Classic 重复 bootstrap。 */
  const timelineSnapshotRef = useRef<EditTimelineData | null>(null);
  if (timeline && timelineSnapshotRef.current === null) {
    timelineSnapshotRef.current = timeline;
  }

  useEffect(() => {
    void fetchEditCapabilities().then(setCapabilities);
  }, []);

  useEffect(() => {
    const cached = getClassicEditorModule();
    const promise = cached ?? prefetchClassicEditor();
    void promise
      .then((mod) => setClassicEditor(mod))
      .catch((e) => setLoadError(e instanceof Error ? e.message : String(e)));
  }, []);

  const handleSave = useCallback(
    async (next: Parameters<EditTimelineApi["saveTimeline"]>[0]) => saveTimeline(next),
    [saveTimeline],
  );

  const handleDone = useCallback(async () => {
    const bridgeTl = getClassicBridgeTimeline(projectId, scriptId);
    const toFlush = bridgeTl ?? timeline;
    if (toFlush) await flushSave(toFlush);
    onClose(true);
  }, [projectId, scriptId, timeline, flushSave, onClose]);

  const handleExport = async () => {
    setExporting(true);
    setExportMsg("");
    try {
      const bridgeTl = getClassicBridgeTimeline(projectId, scriptId);
      const toFlush = bridgeTl ?? timeline;
      if (toFlush) await flushSave(toFlush);
      const url = await exportVideo();
      setExportMsg(url ? t("editor:exportDoneFfmpeg") : t("editor:exportDoneFfmpegShort"));
    } catch (e) {
      setExportMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setExporting(false);
    }
  };

  const handleExportNle = async () => {
    setExportingNle(true);
    setExportMsg("");
    try {
      const bridgeTl = getClassicBridgeTimeline(projectId, scriptId);
      const toFlush = bridgeTl ?? timeline;
      if (toFlush) await flushSave(toFlush);
      const url = await exportNleProject();
      setExportMsg(url ? t("editor:exportNleDone") : t("editor:exportNleDoneShort"));
    } catch (e) {
      setExportMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setExportingNle(false);
    }
  };

  const exportEnabled = capabilities?.export_enabled !== false;
  const nleExportEnabled = capabilities?.nle_export_enabled !== false;
  const ffmpegHint = t("editor:ffmpegHintShort");

  const noTimelineHint = error || t("editor:noTimelineHint");

  return (
    <div className={`editor-studio-content ${shellClassName}`.trim()}>
      <header className="svf-studio-chrome">
        <div className="svf-studio-chrome-brand">
          <span className="svf-studio-chrome-rec" aria-hidden />
          <h2>{t("editor:proEditorTitle")}</h2>
        </div>
        <div className="svf-studio-chrome-meta">
          {saving && <span className="status-badge running">{t("common:actions.saving")}</span>}
          {exportMsg && <span className="status-badge muted-badge">{exportMsg}</span>}
          {loadStage !== "ready" && loadStage !== "error" && ClassicEditor && (
            <span className="status-badge muted-badge">{t("common:actions.loading")}</span>
          )}
          {!exportEnabled && (
            <span className="status-badge style-locked" title={ffmpegHint}>
              导出不可用
            </span>
          )}
        </div>
        <div className="svf-studio-chrome-actions">
          <div className="svf-studio-chrome-group">
            <ThemeToggle />
            <LocaleSwitcher className="locale-switcher locale-switcher--compact" />
          </div>
          {showOpenInNewTab && (
            <div className="svf-studio-chrome-group">
              <button
                type="button"
                className="btn-secondary btn-sm"
                title={t("editor:newTabTitle")}
                onClick={() => openEditorStudioInNewTab(projectId, scriptId)}
              >
                {t("nav:openInNewTab")}
              </button>
            </div>
          )}
          <div className="svf-studio-chrome-group">
            <button
              type="button"
              className="btn-secondary btn-sm"
              disabled={exporting || !exportEnabled}
              title={!exportEnabled ? ffmpegHint : t("editor:ffmpegExportTitle")}
              onClick={() => void handleExport()}
            >
              {exporting ? t("editor:studioExporting") : t("editor:studioExportMp4")}
            </button>
            <button
              type="button"
              className="btn-secondary btn-sm"
              disabled={exportingNle || exporting || !nleExportEnabled}
              title={t("editor:exportNlePremiereHint")}
              onClick={() => void handleExportNle()}
            >
              {exportingNle ? t("editor:exportNleExporting") : t("editor:studioExportNlePremiere")}
            </button>
            <button type="button" className="btn-primary btn-sm" onClick={() => void handleDone()}>
              {t("editor:doneClose")}
            </button>
            <button type="button" className="btn-secondary btn-sm" onClick={() => onClose(false)}>
              {t("common:actions.cancel")}
            </button>
          </div>
        </div>
      </header>
      <div className="svf-studio-stage editor-studio-content-body">
        {loadError && (
          <div className="classic-load-error">
            <p className="board-error">无法加载编辑器模块：{loadError}</p>
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={() => {
                setLoadError(null);
                void prefetchClassicEditor()
                  .then((mod) => setClassicEditor(mod))
                  .catch((e) => setLoadError(e instanceof Error ? e.message : String(e)));
              }}
            >
              {t("common:actions.retry")}
            </button>
          </div>
        )}
        {!loadError && loading && !timelineSnapshotRef.current && (
          <p className="muted">正在加载剪辑时间轴…</p>
        )}
        {!loadError && !loading && !timelineSnapshotRef.current && (
          <div className="classic-load-error">
            <p className="board-error">{noTimelineHint}</p>
            <p className="muted text-sm">
              请确认后端 API 已启动（<code>dev.bat</code> 或 <code>uvicorn apps.api.main:app --port 8000</code>），且该剧本已生成剪辑时间轴。
            </p>
            <button type="button" className="btn-secondary btn-sm" onClick={() => void fetchTimeline()}>
              {t("editor:retryLoad")}
            </button>
          </div>
        )}
        {!loadError && ClassicEditor && timelineSnapshotRef.current && (
          <ClassicEditor.SvfClassicEditor
            projectId={projectId}
            scriptId={scriptId}
            initialTimeline={timelineSnapshotRef.current}
            onSave={handleSave}
            onDone={() => void handleDone()}
            onStageChange={setLoadStage}
            chromeMode="standalone"
          />
        )}
        {!loadError && !ClassicEditor && timelineSnapshotRef.current && (
          <p className="muted">{t("editor:loadingClassic")}</p>
        )}
      </div>
    </div>
  );
}
