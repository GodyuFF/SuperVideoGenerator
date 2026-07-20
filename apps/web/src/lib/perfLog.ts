/** 前端性能观测：控制台输出 [PERF:类别] 日志，便于首屏与 API 耗时排查。 */

const ENABLED =
  import.meta.env.DEV || import.meta.env.VITE_PERF_LOG === "1";

/** 是否启用前端性能日志（开发模式默认开启）。 */
export function perfEnabled(): boolean {
  return ENABLED;
}

/** 输出结构化性能日志到浏览器控制台。 */
export function logPerf(
  category: string,
  message: string,
  fields?: Record<string, string | number | boolean | undefined>,
): void {
  if (!ENABLED) return;
  const suffix = fields
    ? ` ${Object.entries(fields)
        .filter(([, value]) => value !== undefined)
        .map(([key, value]) => `${key}=${value}`)
        .join(" ")}`
    : "";
  console.info(`[PERF:${category}] ${message}${suffix}`);
}

/** 测量异步函数耗时并写入 perf 日志。 */
export async function perfMeasure<T>(
  category: string,
  message: string,
  fn: () => Promise<T>,
  fields?: Record<string, string | number | boolean | undefined>,
): Promise<T> {
  const start = performance.now();
  try {
    return await fn();
  } finally {
    logPerf(category, message, {
      ...fields,
      duration_ms: Math.round(performance.now() - start),
    });
  }
}

/** 记录页面/组件挂载后的首屏就绪时间点。 */
export function logPerfMark(category: string, message: string, mark: string): void {
  if (!ENABLED || typeof performance === "undefined") return;
  performance.mark(mark);
  logPerf(category, message, { mark });
}

/** 计算两个 performance mark 之间的耗时。 */
export function logPerfBetween(
  category: string,
  message: string,
  startMark: string,
  endMark: string,
  fields?: Record<string, string | number | boolean | undefined>,
): void {
  if (!ENABLED || typeof performance === "undefined") return;
  try {
    performance.measure(`${startMark}->${endMark}`, startMark, endMark);
    const entries = performance.getEntriesByName(`${startMark}->${endMark}`);
    const last = entries[entries.length - 1];
    if (last) {
      logPerf(category, message, {
        ...fields,
        duration_ms: Math.round(last.duration),
      });
    }
  } catch {
    // mark 不存在时忽略
  }
}

const wsEventCounts = new Map<string, number>();
let wsSummaryTimer: ReturnType<typeof setInterval> | null = null;

/** 记录 WebSocket 事件类型计数（每 5s 汇总输出）。 */
export function recordWsEvent(type: string): void {
  if (!ENABLED) return;
  const key = type || "unknown";
  wsEventCounts.set(key, (wsEventCounts.get(key) ?? 0) + 1);
  if (!wsSummaryTimer) {
    wsSummaryTimer = setInterval(() => {
      if (wsEventCounts.size === 0) return;
      const summary = Object.fromEntries(wsEventCounts);
      wsEventCounts.clear();
      logPerf("workbench", "ws_event_summary", summary);
    }, 5000);
  }
}
