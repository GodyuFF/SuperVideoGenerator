/**
 * 轻量剪辑 Tab WebSocket 绑定：监听 svg:ws-event，不静态加载 OpenCut Core。
 */

const wsHandlers = new Map<string, () => void>();
const reloadState = new Map<
  string,
  { timer: ReturnType<typeof setTimeout> | null; lastRevision: unknown }
>();

const RELOAD_DEBOUNCE_MS = 500;

/** 生成项目+剧本维度的 WS 绑定键。 */
function wsKey(projectId: string, scriptId: string): string {
  return `${projectId}:${scriptId}`;
}

/** 防抖调度时间轴 API 重载，并按 revision 去重。 */
function scheduleDebouncedReload(
  projectId: string,
  scriptId: string,
  revision: unknown,
): void {
  const key = wsKey(projectId, scriptId);
  let state = reloadState.get(key);
  if (!state) {
    state = { timer: null, lastRevision: null };
    reloadState.set(key, state);
  }

  if (
    revision != null &&
    state.lastRevision != null &&
    revision === state.lastRevision
  ) {
    return;
  }

  if (state.timer) clearTimeout(state.timer);
  state.timer = setTimeout(() => {
    state!.timer = null;
    if (revision != null) {
      state!.lastRevision = revision;
    }
    void import("./agentBridge").then(({ reloadFromApi }) =>
      reloadFromApi(projectId, scriptId),
    );
  }, RELOAD_DEBOUNCE_MS);
}

/** 绑定 edit_timeline_updated 等 WS 事件，触发时间轴热更新。 */
export function bindEditWsEvents(projectId: string, scriptId: string): void {
  const key = wsKey(projectId, scriptId);
  if (wsHandlers.has(key)) return;

  const handler = (ev: Event) => {
    const detail = (ev as CustomEvent).detail as {
      type?: string;
      script_id?: string;
      revision?: unknown;
    };
    if (detail?.type !== "edit_timeline_updated") return;
    if (detail.script_id && detail.script_id !== scriptId) return;
    scheduleDebouncedReload(projectId, scriptId, detail.revision);
  };

  window.addEventListener("svg:ws-event", handler);
  wsHandlers.set(key, () => {
    window.removeEventListener("svg:ws-event", handler);
    const state = reloadState.get(key);
    if (state?.timer) clearTimeout(state.timer);
    reloadState.delete(key);
  });
}

/** 解除 WS 事件绑定。 */
export function unbindEditWsEvents(projectId: string, scriptId: string): void {
  const key = wsKey(projectId, scriptId);
  wsHandlers.get(key)?.();
  wsHandlers.delete(key);
}
