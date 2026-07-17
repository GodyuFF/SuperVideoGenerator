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

/** window.svfDesktop 契约。 */
export interface SvfDesktopApi {
  isDesktop: true;
  /** 从本机 data/ 读媒体，供剪辑水合跳过 HTTP。 */
  readLocalMedia: (urlOrPath: string) => Promise<DesktopMediaBytes>;
  /** 桌面运行时信息。 */
  getInfo: () => Promise<SvfDesktopInfo>;
  /** 应用版本号。 */
  getVersion: () => Promise<string>;
}

declare global {
  interface Window {
    svfDesktop?: SvfDesktopApi;
  }
}

export {};
