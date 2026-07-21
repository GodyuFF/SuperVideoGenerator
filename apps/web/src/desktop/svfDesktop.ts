/**
 * 检测并访问 Electron 桌面桥接。
 */

import "./types";
import type {
  DesktopUpdateCheckResult,
  DesktopUpdateState,
  SvfDesktopApi,
  SvfDesktopInfo,
} from "./types";

export type {
  DesktopMediaBytes,
  DesktopQuitInstallResult,
  DesktopUpdateCheckResult,
  DesktopUpdateState,
  DesktopUpdateStatus,
  SvfDesktopApi,
  SvfDesktopInfo,
} from "./types";

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

/** 是否为已打包桌面应用（可检查更新）。 */
export async function isPackagedDesktopApp(): Promise<boolean> {
  const api = getSvfDesktop();
  if (!api) return false;
  const info = await api.getInfo();
  return info.packaged;
}

/** 拉取当前自动更新状态。 */
export async function getDesktopUpdateState(): Promise<DesktopUpdateState | null> {
  const api = getSvfDesktop();
  if (!api) return null;
  return api.getUpdateState();
}

/** 触发 GitHub Releases 更新检查。 */
export async function checkDesktopUpdates(): Promise<DesktopUpdateCheckResult | null> {
  const api = getSvfDesktop();
  if (!api) return null;
  return api.checkForUpdates();
}

/**
 * 在系统浏览器中打开外链。
 * 桌面壳走 shell.openExternal；普通 Web 用 window.open 新标签。
 */
export async function openInSystemBrowser(url: string): Promise<void> {
  const api = getSvfDesktop();
  if (api?.openExternalUrl) {
    const result = await api.openExternalUrl(url);
    if (!result.ok) {
      throw new Error(result.message || "无法打开外链");
    }
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}
