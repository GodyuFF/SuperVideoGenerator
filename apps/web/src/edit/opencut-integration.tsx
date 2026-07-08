/**
 * OpenCut 编辑器 iframe 宿主组件。
 *
 * 管理 iframe 生命周期、建立 postMessage 通信桥、
 * 处理加载/错误/重连状态。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  type BridgeEvent,
  type BridgeCommand,
  type OpenCutBridge,
  type OpenCutProject,
  createOpenCutBridge,
} from "./opencut-bridge";

export interface OpenCutIntegrationProps {
  project: OpenCutProject;
  editorUrl?: string;
  className?: string;
  /** Agent 发送的命令，组件通过 postMessage 转发给编辑器 */
  pendingCommand?: BridgeCommand | null;
  onCommandHandled?: () => void;
  onTimelineChanged?: (state: BridgeEvent & { type: "timeline_changed" }) => void;
  onExportComplete?: (url: string) => void;
  onExportProgress?: (pct: number, msg: string) => void;
  onError?: (message: string) => void;
  onReady?: () => void;
}

type ConnectionState = "loading" | "connecting" | "ready" | "error" | "disconnected";

const DEFAULT_EDITOR_URL = "http://localhost:5173/editor";

export function OpenCutIntegration({
  project,
  editorUrl = DEFAULT_EDITOR_URL,
  className,
  pendingCommand,
  onCommandHandled,
  onTimelineChanged,
  onExportComplete,
  onExportProgress,
  onError,
  onReady,
}: OpenCutIntegrationProps) {
  const [connectionState, setConnectionState] = useState<ConnectionState>("loading");
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const bridgeRef = useRef<OpenCutBridge | null>(null);
  const readyRef = useRef(false);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleEvent = useCallback(
    (event: BridgeEvent) => {
      switch (event.type) {
        case "ready":
          setConnectionState("ready");
          readyRef.current = true;
          // Load project once editor is ready
          bridgeRef.current?.send({ type: "load_project", project });
          onReady?.();
          break;
        case "pong":
          if (connectionState === "disconnected") {
            setConnectionState("ready");
          }
          break;
        case "timeline_changed":
          onTimelineChanged?.(event);
          break;
        case "export_progress":
          onExportProgress?.(event.pct, event.msg);
          break;
        case "export_complete":
          onExportComplete?.(event.url);
          break;
        case "export_error":
          onError?.(event.error);
          break;
        case "error":
          onError?.(event.message);
          break;
      }
    },
    [project, connectionState, onTimelineChanged, onExportComplete, onExportProgress, onError, onReady],
  );

  // Initialize bridge when iframe loads
  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;

    const bridge = createOpenCutBridge({
      iframe,
      editorOrigin: new URL(editorUrl).origin,
    });

    bridgeRef.current = bridge;
    setConnectionState("connecting");

    const unsub = bridge.on(handleEvent);

    return () => {
      unsub();
      bridge.destroy();
      bridgeRef.current = null;
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current);
      }
    };
  }, [editorUrl, handleEvent]);

  // Forward pending commands from Agent
  useEffect(() => {
    if (!pendingCommand || !bridgeRef.current || !readyRef.current) return;
    bridgeRef.current.send(pendingCommand);
    onCommandHandled?.();
  }, [pendingCommand, onCommandHandled]);

  // Handle iframe load errors
  const handleIframeError = useCallback(() => {
    setConnectionState("error");
    onError?.("OpenCut 编辑器加载失败");
  }, [onError]);

  // Retry loading
  const handleRetry = useCallback(() => {
    if (!iframeRef.current) return;
    setConnectionState("loading");
    iframeRef.current.src = editorUrl;
  }, [editorUrl]);

  return (
    <div className={`opencut-integration ${className ?? ""}`}>
      {/* Loading overlay */}
      {connectionState === "loading" && (
        <div className="opencut-loading">
          <span className="opencut-loading-spinner" />
          <p>正在加载剪辑编辑器…</p>
        </div>
      )}

      {/* Error overlay */}
      {connectionState === "error" && (
        <div className="opencut-error">
          <p>编辑器加载失败</p>
          <button type="button" className="btn-secondary btn-sm" onClick={handleRetry}>
            重试
          </button>
        </div>
      )}

      {/* Disconnected overlay */}
      {connectionState === "disconnected" && (
        <div className="opencut-disconnected">
          <p>编辑器连接中断，正在重连…</p>
        </div>
      )}

      {/* Editor iframe */}
      <iframe
        ref={iframeRef}
        src={editorUrl}
        className="opencut-iframe"
        title="OpenCut Editor"
        sandbox="allow-scripts allow-same-origin"
        allow="clipboard-write"
        onError={handleIframeError}
        style={{
          width: "100%",
          height: "100%",
          border: "none",
          display: connectionState === "error" ? "none" : "block",
        }}
      />
    </div>
  );
}
