/** Classic MediaTime ticks 与毫秒换算（与 OpenCut wasm TICKS_PER_SECOND 一致）。 */

import { TICKS_PER_SECOND } from "@opencut/wasm";

/** 毫秒转 Classic MediaTime ticks。 */
export function msToTicks(ms: number): number {
  return Math.round((ms / 1000) * TICKS_PER_SECOND);
}

/** Classic MediaTime ticks 转毫秒。 */
export function ticksToMs(ticks: number): number {
  return Math.round((ticks / TICKS_PER_SECOND) * 1000);
}

export { TICKS_PER_SECOND };
