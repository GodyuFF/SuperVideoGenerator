/** SVF 集成的 OpenCut Classic 编辑器入口。 */

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { EditorProvider } from "@opencut/components/providers/editor-provider";
import { ClassicEditorErrorBoundary } from "./ClassicEditorErrorBoundary";
import { SvfClassicEditorShell } from "./SvfClassicEditorShell";
import { svfProjectKey } from "../adapter/svfProjectAdapter";
import {
  installSvfStorageBridge,
  registerSvfSaveHandler,
  acquireSvfEditorSession,
  releaseSvfEditorSession,
  markSvfProjectLoaded,
} from "./svf-storage-bridge";
import { warmGpuRenderer } from "../classicPrefetch";
import {
  registerClassicAgentSession,
  unregisterClassicAgentSession,
} from "../classicAgentBridge";
import type { EditTimelineData } from "../../edit/types";
import { useTranslation } from "react-i18next";
import "@opencut/globals.css";
import "./svf-opencut-theme.css";

export type ClassicLoadStage =
  | "module"
  | "bridge"
  | "wasm"
  | "project"
  | "ready"
  | "error";

interface SvfClassicEditorProps {
  projectId: string;
  scriptId: string;
  initialTimeline?: EditTimelineData;
  onSave: (timeline: EditTimelineData) => Promise<EditTimelineData | void>;
  onDone: () => void;
  onStageChange?: (stage: ClassicLoadStage) => void;
  /** bridge 从 API 装填后同步 revision，避免 PATCH 409。 */
  onRevisionSync?: (revision: number) => void;
  /** standalone：外层 SVF chrome 已含导出/完成，隐藏内层顶栏。 */
  chromeMode?: "embedded" | "standalone";
  /** 外层顶栏导出按钮挂载点（Portal）。 */
  exportHost?: HTMLDivElement | null;
}

const STAGE_KEYS: Record<ClassicLoadStage, string> = {
  module: "classicStage.module",
  bridge: "classicStage.bridge",
  wasm: "classicStage.wasm",
  project: "classicStage.project",
  ready: "classicStage.ready",
  error: "classicStage.error",
};

/** 在 SVF 弹窗内挂载完整 OpenCut Classic 编辑器。 */
export function SvfClassicEditor({
  projectId,
  scriptId,
  initialTimeline,
  onSave,
  onDone,
  onStageChange,
  onRevisionSync,
  chromeMode = "standalone",
  exportHost = null,
}: SvfClassicEditorProps) {
  const { t } = useTranslation("editor");
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stage, setStage] = useState<ClassicLoadStage>("module");
  const [retryKey, setRetryKey] = useState(0);
  const [bootstrapId, setBootstrapId] = useState(0);
  const compositeId = svfProjectKey(projectId, scriptId);
  const sessionHeldRef = useRef(false);

  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;

  const onStageChangeRef = useRef(onStageChange);
  onStageChangeRef.current = onStageChange;

  const onRevisionSyncRef = useRef(onRevisionSync);
  onRevisionSyncRef.current = onRevisionSync;

  /** 弹窗打开时快照 timeline，避免保存后 prop 引用变化触发重复 bootstrap。 */
  const bootstrapTimelineRef = useRef<EditTimelineData | undefined>(initialTimeline);

  const reportStage = useCallback((next: ClassicLoadStage) => {
    setStage(next);
    onStageChangeRef.current?.(next);
  }, []);

  useEffect(() => {
    if (retryKey > 0) {
      bootstrapTimelineRef.current = initialTimeline;
    } else if (bootstrapTimelineRef.current === undefined && initialTimeline) {
      bootstrapTimelineRef.current = initialTimeline;
    }
  }, [initialTimeline, retryKey]);

  useEffect(() => {
    let cancelled = false;

    registerSvfSaveHandler(async (timeline) => onSaveRef.current(timeline));
    registerClassicAgentSession(projectId, scriptId);

    void (async () => {
      try {
        reportStage("bridge");
        const base = await installSvfStorageBridge(projectId, scriptId, {
          force: true,
        });
        onRevisionSyncRef.current?.(base.revision ?? 0);
        if (cancelled) return;

        reportStage("wasm");
        await warmGpuRenderer();
        if (cancelled) return;

        reportStage("project");
        markSvfProjectLoaded(compositeId);
        acquireSvfEditorSession(projectId, scriptId);
        sessionHeldRef.current = true;
        if (!cancelled) {
          setBootstrapId((id) => id + 1);
          setReady(true);
          reportStage("ready");
        }
      } catch (e) {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : String(e);
          setError(msg);
          reportStage("error");
        }
      }
    })();

    return () => {
      cancelled = true;
      unregisterClassicAgentSession(projectId, scriptId);
      if (sessionHeldRef.current) {
        releaseSvfEditorSession(projectId, scriptId);
        sessionHeldRef.current = false;
      }
    };
  }, [projectId, scriptId, compositeId, retryKey, reportStage]);

  if (error) {
    return (
      <div className="classic-load-error flex flex-1 flex-col items-center justify-center gap-2 p-6">
        <p className="board-error">{t("classicLoadFailed", { error })}</p>
        <p className="muted text-sm">{t("classicLoadHint")}</p>
        <button
          type="button"
          className="btn-secondary btn-sm"
          onClick={() => {
            bootstrapTimelineRef.current = initialTimeline;
            setError(null);
            setReady(false);
            reportStage("module");
            setRetryKey((k) => k + 1);
          }}
        >
          {t("retryLoad")}
        </button>
      </div>
    );
  }

  if (!ready) {
    return (
      <div className="classic-load-progress muted flex flex-1 flex-col items-center justify-center p-6">
        <p>{t(STAGE_KEYS[stage])}</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Suspense fallback={<p className="muted p-6">{t("classicInitComponents")}</p>}>
        <ClassicEditorErrorBoundary
          onRetry={() => {
            bootstrapTimelineRef.current = initialTimeline;
            setReady(false);
            setRetryKey((k) => k + 1);
          }}
        >
          <EditorProvider
            key={`${compositeId}-${bootstrapId}-${retryKey}`}
            projectId={compositeId}
            embedded
          >
            <SvfClassicEditorShell
              onDone={onDone}
              displayName={scriptId}
              chromeMode={chromeMode}
              exportHost={exportHost}
            />
          </EditorProvider>
        </ClassicEditorErrorBoundary>
      </Suspense>
    </div>
  );
}

export { STAGE_KEYS };
