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
import { svfProjectKey, buildTimelineFingerprint } from "./adapter/svfProjectAdapter";
import {
  installSvfStorageBridge,
  registerSvfSaveHandler,
  acquireSvfEditorSession,
  releaseSvfEditorSession,
  markSvfProjectLoaded,
} from "./opencut/svf-storage-bridge";
import {
  getSvfProjectMediaCache,
  getMediaHydrationIssues,
  listMediaHydrationMessageKeys,
} from "./adapter/SvfMediaBridge";
import { warmGpuRenderer } from "./classicPrefetch";
import {
  registerClassicAgentSession,
  unregisterClassicAgentSession,
} from "./classicAgentBridge";
import type { EditTimelineData } from "../edit/types";
import { EditTabExportPortal } from "./EditTabExportPortal";
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
  /** 播放头、总时长与播放状态变化时回调（毫秒均来自 EditorCore MediaTime）。 */
  onPlaybackChange?: (state: {
    playheadMs: number;
    durationMs: number;
    playing: boolean;
  }) => void;
  /** 顶栏导出按钮 Portal 挂载点（已挂载的 DOM 元素）。 */
  exportHost?: HTMLDivElement | null;
  /** Tab 内 Classic 编辑保存回调（PATCH edit-timeline）。 */
  onSaveTimeline?: (timeline: EditTimelineData) => Promise<EditTimelineData | void>;
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

/** 订阅 OpenCut 播放状态并上报给父组件（含播放中的逐帧 onUpdate）。 */
function PlaybackReporter({
  onPlaybackChange,
}: {
  onPlaybackChange?: (state: {
    playheadMs: number;
    durationMs: number;
    playing: boolean;
  }) => void;
}) {
  const onChangeRef = useRef(onPlaybackChange);
  onChangeRef.current = onPlaybackChange;

  useEffect(() => {
    let alive = true;
    const unsubs: Array<() => void> = [];

    void (async () => {
      const { editor, mediaTimeToSeconds } = await getPlaybackApi();
      if (!alive) return;

      /** 从 EditorCore 读取播放头与场景总时长（ticks → 毫秒）。 */
      const emit = () => {
        const playheadMs =
          mediaTimeToSeconds({ time: editor.playback.getCurrentTime() }) * 1000;
        const durationMs =
          mediaTimeToSeconds({ time: editor.timeline.getTotalDuration() }) * 1000;
        onChangeRef.current?.({
          playheadMs,
          durationMs,
          playing: editor.playback.getIsPlaying(),
        });
      };

      emit();
      unsubs.push(editor.playback.subscribe(emit));
      unsubs.push(editor.playback.onUpdate(() => emit()));
      unsubs.push(editor.playback.onSeek(() => emit()));
      unsubs.push(editor.timeline.subscribe(emit));
    })();

    return () => {
      alive = false;
      for (const off of unsubs) off();
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
    { projectId, scriptId, timeline, paused = false, holdSessionOnPause = false, onPlaybackChange, onSaveTimeline, exportHost },
    ref,
  ) {
    const { t } = useAppTranslation(["editor", "common"]);
    const themeClass = useResolvedSvfTheme();
    const [ready, setReady] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [hydrationMessageKeys, setHydrationMessageKeys] = useState<string[]>([]);
    const [retryKey, setRetryKey] = useState(0);
    /** bridge 就绪后才递增，避免 EditorProvider 在缓存未装好时抢跑 loadProject。 */
    const [bootstrapId, setBootstrapId] = useState(0);
    const compositeId = svfProjectKey(projectId, scriptId);
    const sessionHeldRef = useRef(false);
    const bootstrapTimelineRef = useRef(timeline);
    bootstrapTimelineRef.current = timeline;
    const timelineFingerprint = buildTimelineFingerprint(timeline);
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
      registerSvfSaveHandler(async (merged) => {
        if (!onSaveTimeline) return undefined;
        return onSaveTimeline(merged);
      });

      return () => {
        unregisterClassicAgentSession(projectId, scriptId);
      };
    }, [projectId, scriptId, paused, onSaveTimeline]);

    useEffect(() => {
      if (paused) {
        setReady(false);
        return;
      }

      let cancelled = false;
      setReady(false);
      setError(null);

      /** 弹窗刚关闭时延后一帧再装 bridge，避免与 EditorStudio 卸载争抢主线程。 */
      const deferId = window.requestAnimationFrame(() => {
        void (async () => {
          try {
            const base = await installSvfStorageBridge(projectId, scriptId, {
              force: true,
              initialTimeline: bootstrapTimelineRef.current,
            });
            bootstrapTimelineRef.current = base;
            if (cancelled) return;

            await warmGpuRenderer();
            if (cancelled) return;

            markSvfProjectLoaded(compositeId);
            acquireSvfEditorSession(projectId, scriptId);
            sessionHeldRef.current = true;
            const issues = getMediaHydrationIssues(getSvfProjectMediaCache(compositeId));
            if (!cancelled) {
              setHydrationMessageKeys(listMediaHydrationMessageKeys(issues));
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
      });

      return () => {
        cancelled = true;
        window.cancelAnimationFrame(deferId);
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
            >
              {hydrationMessageKeys.map((key) => (
                <p key={key} className="svf-media-hydration-warn px-3 py-2 text-sm">
                  {t(`editor:${key}`)}
                </p>
              ))}
              <PlaybackReporter onPlaybackChange={onPlaybackChange} />
              <EditTabExportPortal host={exportHost ?? null} />
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
