/**
 * OpenCut Classic 预加载：在剪辑 Tab 空闲时预热 chunk 与 WASM。
 */

let classicModulePromise: Promise<typeof import("./opencut/SvfClassicEditor")> | null = null;
let gpuWarmPromise: Promise<void> | null = null;

/** 预加载 Classic 编辑器 chunk（幂等）。 */
export function prefetchClassicEditor(): Promise<typeof import("./opencut/SvfClassicEditor")> {
  if (!classicModulePromise) {
    classicModulePromise = import("./opencut/SvfClassicEditor");
  }
  return classicModulePromise;
}

/** 预热 opencut-wasm GPU 渲染器（幂等）。 */
export function warmGpuRenderer(): Promise<void> {
  if (!gpuWarmPromise) {
    gpuWarmPromise = import("@opencut/services/renderer/gpu-renderer").then((mod) =>
      mod.initializeGpuRenderer(),
    );
  }
  return gpuWarmPromise;
}

/** 并行预加载 Classic 模块与 WASM。 */
export function prefetchClassicStudio(): void {
  void prefetchClassicEditor();
  void warmGpuRenderer();
}

/** 获取已缓存的 Classic 模块 promise（若尚未开始则返回 null）。 */
export function getClassicEditorModule():
  | Promise<typeof import("./opencut/SvfClassicEditor")>
  | null {
  return classicModulePromise;
}

