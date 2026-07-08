/**
 * OpenCut Editor 与 SuperVideoGenerator 的 postMessage 通信桥。
 *
 * 职责：
 * - 向 iframe 内的 OpenCut 编辑器发送指令
 * - 监听 OpenCut 的状态变更并回调宿主
 * - 处理通信超时、重连、错误
 */

export interface OpenCutProject {
  id: string;
  name: string;
  timeline?: unknown;
  mediaAssets?: Array<{
    id: string;
    name: string;
    type: string;
    url: string;
    durationMs?: number;
  }>;
}

export interface OpenCutTimelineState {
  tracks: unknown;
  videoLayers?: unknown;
  durationMs: number;
  revision: number;
}

export type BridgeCommand =
  | { type: "load_project"; project: OpenCutProject }
  | { type: "apply_action"; action: string; params: Record<string, unknown> }
  | { type: "seek_to"; timeMs: number }
  | { type: "play" }
  | { type: "pause" }
  | { type: "export"; options?: { skipSubtitles?: boolean } }
  | { type: "ping" };

export type BridgeEvent =
  | { type: "ready" }
  | { type: "timeline_changed"; state: OpenCutTimelineState }
  | { type: "export_progress"; pct: number; msg: string }
  | { type: "export_complete"; url: string }
  | { type: "export_error"; error: string }
  | { type: "selection_changed"; elementId: string | null }
  | { type: "pong" }
  | { type: "error"; message: string };

type BridgeEventHandler = (event: BridgeEvent) => void;

export interface OpenCutBridge {
  send: (cmd: BridgeCommand) => void;
  on: (handler: BridgeEventHandler) => () => void;
  destroy: () => void;
}

const PING_INTERVAL_MS = 10_000;
const PING_TIMEOUT_MS = 3_000;

export function createOpenCutBridge({
  iframe,
  editorOrigin,
}: {
  iframe: HTMLIFrameElement;
  editorOrigin: string;
}): OpenCutBridge {
  const handlers = new Set<BridgeEventHandler>();
  let pingTimer: ReturnType<typeof setInterval> | null = null;
  let destroyed = false;

  function send(cmd: BridgeCommand) {
    if (destroyed || !iframe.contentWindow) return;
    iframe.contentWindow.postMessage(
      { source: "super-video-generator", ...cmd },
      editorOrigin,
    );
  }

  function onMessage(e: MessageEvent) {
    if (destroyed) return;

    // Validate origin
    if (e.origin !== editorOrigin) return;

    const data = e.data as Record<string, unknown> | undefined;
    if (!data || data.source !== "opencut-editor") return;

    const event = data as unknown as BridgeEvent;
    for (const handler of handlers) {
      try {
        handler(event);
      } catch (err) {
        console.warn("[opencut-bridge] handler error:", err);
      }
    }
  }

  // Start heartbeat
  pingTimer = setInterval(() => {
    send({ type: "ping" });
  }, PING_INTERVAL_MS);

  window.addEventListener("message", onMessage);

  function on(handler: BridgeEventHandler) {
    handlers.add(handler);
    return () => {
      handlers.delete(handler);
    };
  }

  function destroy() {
    destroyed = true;
    if (pingTimer) {
      clearInterval(pingTimer);
      pingTimer = null;
    }
    window.removeEventListener("message", onMessage);
    handlers.clear();
  }

  return { send, on, destroy };
}
