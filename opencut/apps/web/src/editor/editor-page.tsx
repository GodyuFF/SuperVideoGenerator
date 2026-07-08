/** 编辑器主页面布局 */

import { useEffect, useRef } from "react";
import { initHostBridge } from "./host-bridge";
import { useEditorStore } from "./editor-store";
import { TimelineView } from "../timeline/timeline-view";
import { PreviewCanvas } from "../preview/preview-canvas";
import { MediaPanel } from "../media/media-panel";

export function EditorPage() {
  const store = useEditorStore();
  const rafRef = useRef<number>(0);
  const lastFrameRef = useRef<number>(0);

  // 初始化 postMessage 通信
  useEffect(() => {
    initHostBridge();
  }, []);

  // 播放循环
  useEffect(() => {
    if (!store.isPlaying) return;

    function tick(now: number) {
      if (!lastFrameRef.current) lastFrameRef.current = now;
      const delta = now - lastFrameRef.current;
      lastFrameRef.current = now;

      const nextMs = Math.min(
        store.playheadMs + delta,
        store.timeline.durationMs,
      );
      store.setPlayheadMs(nextMs);

      if (nextMs >= store.timeline.durationMs) {
        store.setPlaying(false);
        lastFrameRef.current = 0;
        return;
      }

      rafRef.current = requestAnimationFrame(tick);
    }

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(rafRef.current);
      lastFrameRef.current = 0;
    };
  }, [store.isPlaying, store.playheadMs, store.timeline.durationMs]);

  const selectedClip = store.timeline.videoLayers
    .flatMap((l) => l.clips)
    .find((c) => c.id === store.selectedClipId);

  return (
    <div className="editor-page">
      {/* 顶部工具栏 */}
      <header className="editor-header">
        <span className="editor-title">OpenCut Editor</span>
        <span className="editor-time">
          {formatMs(store.playheadMs)} / {formatMs(store.timeline.durationMs)}
        </span>
        <button
          type="button"
          className="editor-btn"
          onClick={() => store.togglePlay()}
        >
          {store.isPlaying ? "暂停" : "播放"}
        </button>
      </header>

      {/* 主体：左侧预览 + 中间时间轴 + 右侧属性 */}
      <div className="editor-body">
        <div className="editor-preview-panel">
          <PreviewCanvas
            timeline={store.timeline}
            playheadMs={store.playheadMs}
          />
        </div>

        <div className="editor-main">
          <div className="editor-timeline-wrapper">
            <TimelineView />
          </div>
        </div>

        <div className="editor-sidebar">
          <MediaPanel />
          {selectedClip && (
            <div className="editor-properties">
              <h3>属性</h3>
              <div className="editor-prop-row">
                <span>标签</span>
                <span>{selectedClip.label}</span>
              </div>
              <div className="editor-prop-row">
                <span>时间段</span>
                <span>
                  {formatMs(selectedClip.startMs)} – {formatMs(selectedClip.endMs)}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
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
