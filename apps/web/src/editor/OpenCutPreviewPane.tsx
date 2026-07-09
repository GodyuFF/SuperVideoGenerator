/** 剪辑 Tab 轻量 OpenCut WASM 预览（与专业剪辑弹窗共享 EditorCore）。 */

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { useAppTranslation } from "../i18n/useAppTranslation";
import { TooltipProvider } from "@opencut/components/ui/tooltip";
import { useResolvedSvfTheme } from "../hooks/useResolvedSvfTheme";
import { PreviewPanel } from "@opencut/preview/components";
import { EditorProvider } from "@opencut/components/providers/editor-provider";
import { ClassicEditorErrorBoundary } from "./opencut/ClassicEditorErrorBoundary";
import { svfProjectKey } from "./adapter/svfProjectAdapter";
import {
  installSvfStorageBridge,
  registerSvfSaveHandler,
  acquireSvfEditorSession,
  releaseSvfEditorSession,
  markSvfProjectLoaded,
} from "./opencut/svf-storage-bridge";
import {
  getSvfProjectMediaCache,
  getVideoHydrationState,
  type VideoHydrationState,
} from "./adapter/SvfMediaBridge";
import { warmGpuRenderer } from "./classicPrefetch";
import {
  registerClassicAgentSession,
  unregisterClassicAgentSession,
} from "./classicAgentBridge";
import type { EditTimelineData } from "../edit/types";
import "@opencut/globals.css";
import "./opencut/svf-opencut-theme.css";
import { useSvfOpencutThemeScope } from "./opencut/useSvfOpencutThemeScope";

/** OpenCut 预览播放控制句柄（供剪辑 Tab 工具栏调用）。 */
export interface OpenCutPreviewPaneHandle {
  /** 开始播放。 */
  play(): Promise<void>;
  /** 暂停播放。 */
  pause(): Promise<void>;
  /** 跳转到指定毫秒。 */
  seek(ms: number): Promise<void>;
  /** 读取当前播放头毫秒。 */
  getPlayheadMs(): Promise<number>;
  /** 是否正在播放。 */
  isPlaying(): Promise<boolean>;
}

interface OpenCutPreviewPaneProps {
  projectId: string;
  scriptId: string;
  timeline: EditTimelineData;
  /** 专业剪辑弹窗打开时暂停预览，释放 EditorCore 给弹窗。 */
  paused?: boolean;
  /** 为 true 时暂停不释放 bridge 会话（弹窗接管同一项目）。 */
  holdSessionOnPause?: boolean;
  /** 播放头或播放状态变化时回调。 */
  onPlaybackChange?: (playheadMs: number, playing: boolean) => void;
}

/** 按需加载 EditorCore 与 wasm 时间工具。 */
async function getPlaybackApi() {
  const [coreMod, wasmMod] = await Promise.all([
    import("@opencut/core"),
    import("@opencut/wasm"),
  ]);
  const editor = coreMod.EditorCore.getInstance();
  return {
    editor,
    mediaTimeFromSeconds: wasmMod.mediaTimeFromSeconds,
    mediaTimeToSeconds: wasmMod.mediaTimeToSeconds,
  };
}

/** 订阅 OpenCut 播放状态并上报给父组件。 */
function PlaybackReporter({
  onPlaybackChange,
}: {
  onPlaybackChange?: (playheadMs: number, playing: boolean) => void;
}) {
  const onChangeRef = useRef(onPlaybackChange);
  onChangeRef.current = onPlaybackChange;

  useEffect(() => {
    let alive = true;
    let unsubscribe: (() => void) | undefined;

    void (async () => {
      const { editor, mediaTimeToSeconds } = await getPlaybackApi();
      if (!alive) return;

      const emit = () => {
        const ms = mediaTimeToSeconds({ time: editor.playback.getCurrentTime() }) * 1000;
        onChangeRef.current?.(ms, editor.playback.getIsPlaying());
      };

      emit();
      unsubscribe = editor.playback.subscribe(emit);
    })();

    return () => {
      alive = false;
      unsubscribe?.();
    };
  }, []);

  return null;
}

/** 空操作：Tab 预览不显示 overlay 控件。 */
function noopOverlayVisibilityChange(_params: {
  overlayId: string;
  isVisible: boolean;
}): void {
  return;
}

/** 剪辑 Tab 内嵌 OpenCut WASM 预览面板。 */
export const OpenCutPreviewPane = forwardRef<OpenCutPreviewPaneHandle, OpenCutPreviewPaneProps>(
  function OpenCutPreviewPane(
    { projectId, scriptId, timeline, paused = false, holdSessionOnPause = false, onPlaybackChange },
    ref,
  ) {
    const { t } = useAppTranslation(["editor", "common"]);
    const themeClass = useResolvedSvfTheme();
    const [ready, setReady] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [hydrationState, setHydrationState] = useState<VideoHydrationState>("none");
    const [retryKey, setRetryKey] = useState(0);
    /** bridge 就绪后才递增，避免 EditorProvider 在缓存未装好时抢跑 loadProject。 */
    const [bootstrapId, setBootstrapId] = useState(0);
    const compositeId = svfProjectKey(projectId, scriptId);
    const sessionHeldRef = useRef(false);
    const bootstrapTimelineRef = useRef(timeline);
    bootstrapTimelineRef.current = timeline;
    const timelineFingerprint = `${timeline.revision ?? 0}:${timeline.updated_at ?? ""}:${timeline.duration_ms ?? 0}`;
    const prevFingerprintRef = useRef("");

    useSvfOpencutThemeScope(!paused && ready);

    useImperativeHandle(ref, () => ({
      async play() {
        const { editor } = await getPlaybackApi();
        editor.playback.play();
      },
      async pause() {
        const { editor } = await getPlaybackApi();
        editor.playback.pause();
      },
      async seek(ms: number) {
        const { editor, mediaTimeFromSeconds } = await getPlaybackApi();
        editor.playback.seek({
          time: mediaTimeFromSeconds({ seconds: ms / 1000 }),
        });
      },
      async getPlayheadMs() {
        const { editor, mediaTimeToSeconds } = await getPlaybackApi();
        return mediaTimeToSeconds({ time: editor.playback.getCurrentTime() }) * 1000;
      },
      async isPlaying() {
        const { editor } = await getPlaybackApi();
        return editor.playback.getIsPlaying();
      },
    }));

    useEffect(() => {
      if (paused) {
        unregisterClassicAgentSession(projectId, scriptId);
        void getPlaybackApi().then(({ editor }) => editor.playback.pause());
        return;
      }

      registerClassicAgentSession(projectId, scriptId);
      registerSvfSaveHandler(async () => undefined);

      return () => {
        unregisterClassicAgentSession(projectId, scriptId);
      };
    }, [projectId, scriptId, paused]);

    useEffect(() => {
      if (paused) {
        setReady(false);
        return;
      }

      let cancelled = false;
      setReady(false);
      setError(null);

      void (async () => {
        try {
          const timelineChanged = prevFingerprintRef.current !== timelineFingerprint;
          prevFingerprintRef.current = timelineFingerprint;
          const force = retryKey > 0 || timelineChanged;
          await installSvfStorageBridge(projectId, scriptId, {
            force,
            initialTimeline: bootstrapTimelineRef.current,
          });
          if (cancelled) return;

          await warmGpuRenderer();
          if (cancelled) return;

          markSvfProjectLoaded(compositeId);
          acquireSvfEditorSession(projectId, scriptId);
          sessionHeldRef.current = true;
          const hydration = getVideoHydrationState(getSvfProjectMediaCache(compositeId));
          if (!cancelled) {
            setHydrationState(hydration);
            setBootstrapId((id) => id + 1);
            setReady(true);
          }
        } catch (e) {
          if (!cancelled) {
            setError(e instanceof Error ? e.message : String(e));
            setReady(false);
          }
        }
      })();

      return () => {
        cancelled = true;
        if (sessionHeldRef.current && !holdSessionOnPause) {
          releaseSvfEditorSession(projectId, scriptId);
          sessionHeldRef.current = false;
        }
      };
    }, [projectId, scriptId, compositeId, retryKey, paused, holdSessionOnPause, timelineFingerprint]);

    if (paused) {
      return (
        <div className="edit-cinema-preview-state edit-tab-preview-paused muted">
          <p>{t("editor:previewPaused")}</p>
        </div>
      );
    }

    if (error) {
      return (
        <div className="edit-cinema-preview-state classic-load-error">
          <p className="board-error">{t("editor:previewFailed", { error })}</p>
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={() => {
              setError(null);
              setReady(false);
              setRetryKey((k) => k + 1);
            }}
          >
            {t("common:actions.retry")}
          </button>
        </div>
      );
    }

    if (!ready) {
      return (
        <div className="edit-cinema-preview-state muted">
          <p>{t("editor:loadingPreview")}</p>
        </div>
      );
    }

    return (
      <ClassicEditorErrorBoundary
        onRetry={() => {
          setReady(false);
          setRetryKey((k) => k + 1);
        }}
      >
        <TooltipProvider delayDuration={300}>
          <div
            className={`svf-opencut-theme opencut-preview-pane ${themeClass} flex flex-1 min-h-0 w-full flex-col overflow-hidden`}
          >
            <EditorProvider
              key={`${compositeId}-${bootstrapId}`}
              projectId={compositeId}
              embedded
              skipStorageMigration
            >
              {hydrationState === "partial" && (
                <p className="svf-media-hydration-warn px-3 py-2 text-sm">
                  {t("editor:mediaHydrationFailedPartial")}
                </p>
              )}
              {hydrationState === "all" && (
                <p className="svf-media-hydration-warn px-3 py-2 text-sm">
                  {t("editor:mediaHydrationFailedAll")}
                </p>
              )}
              <PlaybackReporter onPlaybackChange={onPlaybackChange} />
              <PreviewPanel
                overlayControls={[]}
                overlayInstances={[]}
                onOverlayVisibilityChange={noopOverlayVisibilityChange}
                hideToolbar
              />
            </EditorProvider>
          </div>
        </TooltipProvider>
      </ClassicEditorErrorBoundary>
    );
  },
);
