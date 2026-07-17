/**
 * 检测并访问 Electron 桌面桥接。
 */

import "./types";
import type { SvfDesktopApi, SvfDesktopInfo } from "./types";

export type { DesktopMediaBytes, SvfDesktopApi, SvfDesktopInfo } from "./types";

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

/** 取得应用版本号；非桌面环境返回 null。 */
export async function getSvfDesktopVersion(): Promise<string | null> {
  const api = getSvfDesktop();
  if (!api) return null;
  return api.getVersion();
}
