/**
 * 桌面壳暴露给渲染进程的 API 类型。
 */

/** 主进程读盘返回的媒体字节。 */
export interface DesktopMediaBytes {
  name: string;
  mime: string;
  data: ArrayBuffer;
  absolutePath: string;
  fileUrl: string;
}

/** 桌面运行时信息。 */
export interface SvfDesktopInfo {
  isDesktop: boolean;
  packaged: boolean;
  dataRoot: string;
  webUrl: string;
  repoRoot: string;
  appVersion: string;
}

/** 自动更新状态枚举。 */
export type DesktopUpdateStatus =
  | "idle"
  | "checking"
  | "available"
  | "not-available"
  | "downloading"
  | "downloaded"
  | "error"
  | "disabled";

/** 自动更新完整状态。 */
export interface DesktopUpdateState {
  status: DesktopUpdateStatus;
  currentVersion: string;
  version?: string;
  message?: string;
  percent?: number;
}

/** 手动检查更新返回值。 */
export interface DesktopUpdateCheckResult {
  status: DesktopUpdateStatus;
  version?: string;
  message?: string;
}

/** 退出安装结果。 */
export interface DesktopQuitInstallResult {
  ok: boolean;
  message?: string;
}

/** window.svfDesktop 契约。 */
export interface SvfDesktopApi {
  isDesktop: true;
  /** 从本机 data/ 读媒体，供剪辑水合跳过 HTTP。 */
  readLocalMedia: (urlOrPath: string) => Promise<DesktopMediaBytes>;
  /** 桌面运行时信息。 */
  getInfo: () => Promise<SvfDesktopInfo>;
  /** 应用版本号。 */
  getVersion: () => Promise<string>;
  /** 检查 GitHub Releases 更新。 */
  checkForUpdates: () => Promise<DesktopUpdateCheckResult>;
  /** 获取当前自动更新状态。 */
  getUpdateState: () => Promise<DesktopUpdateState>;
  /** 退出并安装已下载更新。 */
  quitAndInstall: () => Promise<DesktopQuitInstallResult>;
  /** 订阅主进程推送的更新状态。 */
  onUpdateState: (callback: (state: DesktopUpdateState) => void) => () => void;
  /** 通知主进程生成任务是否进行中。 */
  setGenerationBusy: (busy: boolean) => Promise<void>;
  /** 用系统默认浏览器打开 http(s) 外链。 */
  openExternalUrl: (url: string) => Promise<{ ok: boolean; message?: string }>;
}

declare global {
  interface Window {
    svfDesktop?: SvfDesktopApi;
  }
}

export {};
