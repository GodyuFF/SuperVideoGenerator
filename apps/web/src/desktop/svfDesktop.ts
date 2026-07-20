/**
 * 检测并访问 Electron 桌面桥接。
 */

import "./types";
import type { SvfDesktopApi } from "./types";

/** 是否运行在 Electron 壳内。 */
export function isSvfDesktop(): boolean {
  return Boolean(window.svfDesktop?.isDesktop);
}

/** 取得桌面 API；非桌面环境返回 null。 */
export function getSvfDesktop(): SvfDesktopApi | null {
  const api = window.svfDesktop;
  if (!api?.isDesktop) return null;
  return api;
}
