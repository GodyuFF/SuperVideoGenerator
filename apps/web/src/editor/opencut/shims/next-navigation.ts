/** Next.js navigation 兼容层。 */

const stableRouter = {
  push: (_path: string) => undefined,
  replace: (_path: string) => undefined,
  back: () => undefined,
  prefetch: async (_path: string) => undefined,
};

/** 空操作 useRouter（返回稳定引用，避免 effect 依赖抖动）。 */
export function useRouter() {
  return stableRouter;
}

/** useParams 占位。 */
export function useParams(): Record<string, string> {
  return {};
}
