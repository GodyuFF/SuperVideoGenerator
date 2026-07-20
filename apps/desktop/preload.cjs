/**
 * Electron preload：向渲染进程暴露受控桌面 API。
 */

const { contextBridge, ipcRenderer } = require("electron");

/**
 * @typedef {{
 *   name: string;
 *   mime: string;
 *   data: ArrayBuffer;
 *   absolutePath: string;
 *   fileUrl: string;
 * }} DesktopMediaBytes
 */

contextBridge.exposeInMainWorld("svfDesktop", {
  /** 是否运行在 Electron 壳内。 */
  isDesktop: true,
  /**
   * 读取本机媒体文件（跳过 HTTP 水合）。
   * @param {string} urlOrPath API 路径或 projects/... 相对路径
   * @returns {Promise<DesktopMediaBytes>}
   */
  readLocalMedia: (urlOrPath) => ipcRenderer.invoke("media:readLocal", urlOrPath),
  /**
   * 桌面运行时信息。
   * @returns {Promise<{ isDesktop: boolean; dataRoot: string; webUrl: string; repoRoot: string }>}
   */
  getInfo: () => ipcRenderer.invoke("desktop:getInfo"),
});
