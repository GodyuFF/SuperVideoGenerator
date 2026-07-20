/**
 * 防抖异步任务：合并短时间内的重复刷新请求，并串行合并 in-flight 调用。
 */

export interface DebouncedAsyncTask {
  /** 延迟调度执行；多次调用会合并为一次 trailing 执行。 */
  schedule: () => void;
  /** 立即执行（仍参与 in-flight 合并）。 */
  flush: () => Promise<void>;
}

export interface DebouncedAsyncTaskOptions {
  /** 刷新失败时的回调（默认静默）。 */
  onError?: (err: unknown) => void;
}

/** 创建带防抖与 in-flight 合并的异步任务执行器。 */
export function createDebouncedAsyncTask(
  fn: () => Promise<void>,
  delayMs = 400,
  options: DebouncedAsyncTaskOptions = {},
): DebouncedAsyncTask {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let inFlight: Promise<void> | null = null;
  let trailing = false;
  const { onError } = options;

  const run = async (): Promise<void> => {
    if (inFlight) {
      trailing = true;
      return inFlight;
    }
    inFlight = fn()
      .catch((err) => {
        onError?.(err);
      })
      .finally(() => {
        inFlight = null;
        if (trailing) {
          trailing = false;
          void run();
        }
      });
    return inFlight;
  };

  const schedule = (): void => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      void run();
    }, delayMs);
  };

  const flush = async (): Promise<void> => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    await run();
  };

  return { schedule, flush };
}
