/**
 * Agent ↔ 编辑器双向桥：WebSocket 事件、命令执行、时间轴变更通知。
 * Classic 弹窗打开时优先驱动 OpenCut EditorCore（按需 dynamic import）。
 */

import { useEditorStore } from "./editorStore";
import type { EditorEvent, HostCommand } from "./types";
import {
  isClassicAgentSessionActive,
  reloadClassicFromApi,
} from "./classicAgentBridge";
import { svfProjectKey } from "./adapter/svfProjectAdapter";

type TimelineChangeListener = (timeline: unknown) => void;

let listeners: TimelineChangeListener[] = [];
const wsHandlers = new Map<string, () => void>();

/** 按需加载 OpenCut EditorCore，避免进入剪辑 Tab 时同步拉取大包。 */
async function getEditorCore() {
  const mod = await import("@opencut/core");
  return mod.EditorCore;
}

/** 按需加载 OpenCut wasm 时间工具。 */
async function getMediaTimeFromSeconds() {
  const mod = await import("@opencut/wasm");
  return mod.mediaTimeFromSeconds;
}

/** 注册时间轴变更回调（用于 PATCH 持久化）。 */
export function onTimelineChanged(fn: TimelineChangeListener): () => void {
  listeners.push(fn);
  return () => {
    listeners = listeners.filter((l) => l !== fn);
  };
}

/** 通知已注册的时间轴变更监听者。 */
function emitTimelineChanged() {
  const tl = useEditorStore.getState().timeline;
  for (const fn of listeners) fn(tl);
}

/** 向页面广播编辑器事件。 */
function emitEditorEvent(event: EditorEvent) {
  window.dispatchEvent(new CustomEvent("editor:event", { detail: event }));
}

/** 生成 WS 处理器 Map 键。 */
function wsKey(projectId: string, scriptId: string) {
  return `${projectId}:${scriptId}`;
}

/** 绑定 WebSocket 推送：edit_timeline_updated 时刷新编辑器。 */
export function bindAgentWebSocketEvents(
  events: Array<{ type?: string; payload?: unknown }>,
  projectId: string,
  scriptId: string,
) {
  const key = wsKey(projectId, scriptId);
  if (wsHandlers.has(key)) return;

  const handler = async (ev: Event) => {
    const detail = (ev as CustomEvent).detail as { type?: string; script_id?: string };
    if (detail?.type !== "edit_timeline_updated") return;
    if (detail.script_id && detail.script_id !== scriptId) return;
    await reloadFromApi(projectId, scriptId);
    emitEditorEvent({
      source: "video-editor",
      type: "timeline_changed",
      message: "Agent 已更新时间轴",
    });
  };

  window.addEventListener("svg:ws-event", handler);
  wsHandlers.set(key, () => window.removeEventListener("svg:ws-event", handler));

  for (const e of events) {
    if (e.type === "edit_timeline_updated") {
      void reloadFromApi(projectId, scriptId);
    }
  }

  return wsHandlers.get(key);
}

/** 解除 WebSocket 绑定。 */
export function unbindAgentWebSocketEvents(projectId: string, scriptId: string) {
  const key = wsKey(projectId, scriptId);
  wsHandlers.get(key)?.();
  wsHandlers.delete(key);
}

/** 从 API 重新加载时间轴与媒体，并通知各编辑器视图。 */
export async function reloadFromApi(projectId: string, scriptId: string) {
  if (isClassicAgentSessionActive(projectId, scriptId)) {
    const data = await reloadClassicFromApi(projectId, scriptId);
    if (data) {
      window.dispatchEvent(
        new CustomEvent("svg:edit-timeline-reloaded", {
          detail: { projectId, scriptId, timeline: data },
        }),
      );
    }
    return;
  }

  const playhead = useEditorStore.getState().playheadMs;
  const tlRes = await fetch(`/api/projects/${projectId}/scripts/${scriptId}/edit-timeline`);
  if (tlRes.ok) {
    const data = await tlRes.json();
    useEditorStore.getState().setPlayheadMs(Math.min(playhead, data.duration_ms || playhead));
    window.dispatchEvent(
      new CustomEvent("svg:edit-timeline-reloaded", {
        detail: { projectId, scriptId, timeline: data },
      }),
    );
  }
}

/** 执行 Agent 命令（HostCommand 协议）。 */
export function applyAgentCommand(cmd: HostCommand) {
  const store = useEditorStore.getState;

  switch (cmd.type) {
    case "load_project": {
      const project = cmd.project as Record<string, unknown> | undefined;
      const pid = project?.projectId as string | undefined;
      const sid = project?.scriptId as string | undefined;
      if (project?.timeline && pid && sid && isClassicAgentSessionActive(pid, sid)) {
        void reloadClassicFromApi(
          pid,
          sid,
          project.timeline as Parameters<typeof reloadClassicFromApi>[2],
        );
        window.dispatchEvent(new CustomEvent("editor:timeline-changed"));
        break;
      }
      if (project?.timeline) {
        window.dispatchEvent(
          new CustomEvent("svg:edit-timeline-reloaded", {
            detail: { timeline: project.timeline },
          }),
        );
      }
      break;
    }
    case "apply_action": {
      const action = cmd.action as string;
      const params = (cmd.params || {}) as Record<string, unknown>;
      const pid = params.project_id as string | undefined;
      const sid = params.script_id as string | undefined;

      if (pid && sid && isClassicAgentSessionActive(pid, sid)) {
        void reloadClassicFromApi(pid, sid);
        emitEditorEvent({
          source: "video-editor",
          type: "timeline_changed",
          message: `Agent 操作: ${action}`,
        });
        break;
      }

      switch (action) {
        case "seek_to":
          store().setPlayheadMs((params.time_ms as number) || 0);
          break;
        case "play":
          store().setPlaying(true);
          break;
        case "pause":
          store().setPlaying(false);
          break;
        default:
          break;
      }
      emitTimelineChanged();
      window.dispatchEvent(new CustomEvent("editor:timeline-changed"));
      break;
    }
    case "seek_to": {
      const ms = (cmd.timeMs as number) || 0;
      void (async () => {
        const EditorCore = await getEditorCore();
        const mediaTimeFromSeconds = await getMediaTimeFromSeconds();
        EditorCore.getInstance().playback.seek({
          time: mediaTimeFromSeconds({ seconds: ms / 1000 }),
        });
      })();
      store().setPlayheadMs(ms);
      break;
    }
    case "play":
      void (async () => {
        const EditorCore = await getEditorCore();
        EditorCore.getInstance().playback.play();
      })();
      store().setPlaying(true);
      break;
    case "pause":
      void (async () => {
        const EditorCore = await getEditorCore();
        EditorCore.getInstance().playback.pause();
      })();
      store().setPlaying(false);
      break;
    case "ping":
      emitEditorEvent({ source: "video-editor", type: "pong" });
      break;
  }
}

/** 初始化 Agent 桥：监听本地 timeline-changed 事件。 */
export function initAgentBridge() {
  window.addEventListener("editor:timeline-changed", () => emitTimelineChanged());
  emitEditorEvent({ source: "video-editor", type: "ready" });
}

/** 兼容旧 bridge 入口。 */
export function sendCommand(cmd: HostCommand) {
  applyAgentCommand(cmd);
}

/** 解析 Classic 复合项目键（供外部模块使用）。 */
export function classicProjectKey(projectId: string, scriptId: string): string {
  return svfProjectKey(projectId, scriptId);
}

export { applyAgentCommand as applyAgentCommandAlias };
