/** 专业剪辑核心 UI（弹窗与独立页共用）；成片 MP4 仅经 OpenCut 浏览器导出。 */

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useAppTranslation } from "../i18n/useAppTranslation";
import { fetchEditCapabilities } from "./adapter/capabilitiesAdapter";
import { prefetchClassicEditor, getClassicEditorModule } from "./classicPrefetch";
import { getClassicBridgeTimeline } from "./classicAgentBridge";
import { openEditorStudioInNewTab } from "./editorStudioUrls";
import { ThemeToggle } from "../components/theme/ThemeToggle";
import { LocaleSwitcher } from "../i18n/LocaleSwitcher";
import { StudioChromeOverflow } from "./StudioChromeOverflow";
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

  const { timeline, flushSave, saveTimeline, exportNleProject, saveAndRevealExport, saving, loading, error, fetchTimeline, syncRevision } =
    timelineApi;
  const [exportingNle, setExportingNle] = useState(false);
  const [exportHost, setExportHost] = useState<HTMLDivElement | null>(null);

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

  async function deliverExportResult(url: string) {
    const outcome = await saveAndRevealExport(url);
    if (!outcome.revealed) {
      toast.warning(
        t("editor:exportSavedRevealFailed", {
          error: outcome.revealError ?? t("editor:exportRevealUnknown"),
        }),
      );
      return;
    }
    toast.success(t("editor:exportNleSavedAndRevealed"));
  }

  const handleExportNle = async () => {
    setExportingNle(true);
    const loadingToastId = toast.loading(t("editor:exportNleExporting"));
    try {
      const bridgeTl = getClassicBridgeTimeline(projectId, scriptId);
      const toFlush = bridgeTl ?? timeline;
      if (toFlush) await flushSave(toFlush);
      const url = await exportNleProject();
      if (!url) {
        toast.success(t("editor:exportNleDone"));
        return;
      }
      await deliverExportResult(url);
    } catch (e) {
      if (e instanceof Error && e.message === "已取消保存") {
        toast.info(t("editor:exportSaveCancelled"));
      } else {
        toast.error(e instanceof Error ? e.message : String(e));
      }
    } finally {
      toast.dismiss(loadingToastId);
      setExportingNle(false);
    }
  };

  const nleExportEnabled = capabilities?.nle_export_enabled !== false;

  const noTimelineHint = error || t("editor:noTimelineHint");

  return (
    <div className={`editor-studio-content ${shellClassName}`.trim()}>
      <header className="svf-studio-chrome">
        <div className="svf-studio-chrome-brand">
          <span className="svf-studio-chrome-rec" aria-hidden />
          <h2>{t("editor:proEditorTitle")}</h2>
        </div>
        <div className="svf-studio-chrome-status">
          {saving && <span className="status-badge running">{t("common:actions.saving")}</span>}
          {loadStage !== "ready" && loadStage !== "error" && ClassicEditor && (
            <span className="status-badge muted-badge">{t("common:actions.loading")}</span>
          )}
        </div>
        <div className="svf-studio-chrome-actions">
          <div className="svf-studio-chrome-group svf-studio-chrome-utilities">
            <ThemeToggle />
            <LocaleSwitcher className="locale-switcher locale-switcher--compact" />
          </div>
          <div className="svf-studio-chrome-group svf-studio-chrome-workflow">
            <div
              ref={setExportHost}
              className="svf-studio-export-slot"
              aria-label={t("editor:tabExportSlot")}
            />
            <button type="button" className="btn-primary btn-sm" onClick={() => void handleDone()}>
              {t("editor:doneClose")}
            </button>
          </div>
          <StudioChromeOverflow
            showOpenInNewTab={showOpenInNewTab}
            onOpenInNewTab={() => openEditorStudioInNewTab(projectId, scriptId)}
            onExportNle={() => void handleExportNle()}
            exportingNle={exportingNle}
            nleExportEnabled={nleExportEnabled}
            onCancel={() => onClose(false)}
          />
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
              请确认后端 API 已启动（<code>launch-desktop</code> 或 <code>uvicorn apps.api.main:app --port 8000</code>），且该剧本已生成剪辑时间轴。
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
            onRevisionSync={syncRevision}
            onSave={handleSave}
            onDone={() => void handleDone()}
            onStageChange={setLoadStage}
            chromeMode="standalone"
            exportHost={exportHost}
          />
        )}
        {!loadError && !ClassicEditor && timelineSnapshotRef.current && (
          <p className="muted">{t("editor:loadingClassic")}</p>
        )}
      </div>
    </div>
  );
}
