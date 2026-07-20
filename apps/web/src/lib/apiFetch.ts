/** 带指数退避的 API fetch，用于 bootstrap 阶段等待后端就绪。 */

import { logPerf, perfEnabled } from "./perfLog";

export interface ApiFetchOptions {
  /** 最大重试次数（不含首次） */
  retries?: number;
  /** 首次退避毫秒 */
  backoffMs?: number;
}

const RETRYABLE_STATUS = new Set([502, 503, 504]);

function isRetryableError(err: unknown): boolean {
  if (err instanceof TypeError) return true;
  if (err instanceof Error && /fetch|network|Failed/i.test(err.message)) return true;
  return false;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** 对 GET 等 bootstrap 请求做有限重试。 */
export async function apiFetch(
  url: string,
  init?: RequestInit,
  options: ApiFetchOptions = {},
): Promise<Response> {
  const retries = options.retries ?? 3;
  const backoffMs = options.backoffMs ?? 500;
  let lastError: unknown;

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const start = perfEnabled() ? performance.now() : 0;
    try {
      const response = await fetch(url, init);
      if (perfEnabled()) {
        const durationMs = Math.round(performance.now() - start);
        const slow = durationMs >= 500;
        logPerf(
          "api",
          `${init?.method ?? "GET"} ${url}`,
          {
            duration_ms: durationMs,
            status: response.status,
            attempt: attempt + 1,
            slow: slow || undefined,
          },
        );
      }
      if (response.ok || !RETRYABLE_STATUS.has(response.status)) {
        return response;
      }
      lastError = new Error(`HTTP ${response.status}`);
    } catch (err) {
      lastError = err;
      if (!isRetryableError(err)) {
        throw err;
      }
    }
    if (attempt < retries) {
      await sleep(backoffMs * 2 ** attempt);
    }
  }

  if (lastError instanceof Error) {
    throw lastError;
  }
  throw new Error("API 请求失败");
}
