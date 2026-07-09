/**
 * 轻量剪辑 Tab WebSocket 绑定：监听 svg:ws-event，不静态加载 OpenCut Core。
 */

const wsHandlers = new Map<string, () => void>();

/** 生成项目+剧本维度的 WS 绑定键。 */
function wsKey(projectId: string, scriptId: string): string {
  return `${projectId}:${scriptId}`;
}

/** 绑定 edit_timeline_updated 等 WS 事件，触发时间轴热更新。 */
export function bindEditWsEvents(projectId: string, scriptId: string): void {
  const key = wsKey(projectId, scriptId);
  if (wsHandlers.has(key)) return;

  const handler = async (ev: Event) => {
    const detail = (ev as CustomEvent).detail as { type?: string; script_id?: string };
    if (detail?.type !== "edit_timeline_updated") return;
    if (detail.script_id && detail.script_id !== scriptId) return;
    const { reloadFromApi } = await import("./agentBridge");
    await reloadFromApi(projectId, scriptId);
  };

  window.addEventListener("svg:ws-event", handler);
  wsHandlers.set(key, () => window.removeEventListener("svg:ws-event", handler));
}

/** 解除 WS 事件绑定。 */
export function unbindEditWsEvents(projectId: string, scriptId: string): void {
  const key = wsKey(projectId, scriptId);
  wsHandlers.get(key)?.();
  wsHandlers.delete(key);
}
