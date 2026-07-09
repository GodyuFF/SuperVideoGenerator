/**
 * 兼容层：旧 bridge 模块重导出 agentBridge。
 */

import {
  onTimelineChanged as _onTimelineChanged,
  initAgentBridge,
  applyAgentCommand,
  reloadFromApi,
} from "./agentBridge";

export {
  applyAgentCommand,
  applyAgentCommand as sendCommand,
  initAgentBridge as initOpenCutBridge,
  _onTimelineChanged as onTimelineChanged,
  reloadFromApi,
};

/** 兼容旧 BridgeCallbacks 类型。 */
export type BridgeCallbacks = {
  onExport?: () => void;
  onLoadProject?: (projectId: string, scriptId: string) => void;
  onTimelineChanged?: (timeline: unknown) => void;
};

/** 设置外部回调（持久化/加载）。 */
export function setBridgeCallbacks(cb: BridgeCallbacks) {
  if (cb.onTimelineChanged) {
    _onTimelineChanged(cb.onTimelineChanged);
  }
}
