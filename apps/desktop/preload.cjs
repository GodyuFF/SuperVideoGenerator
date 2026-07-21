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
   * @returns {Promise<{ isDesktop: boolean; packaged: boolean; dataRoot: string; webUrl: string; repoRoot: string; appVersion: string }>}
   */
  getInfo: () => ipcRenderer.invoke("desktop:getInfo"),
  /**
   * 应用版本号（与 package.json version 一致）。
   * @returns {Promise<string>}
   */
  getVersion: () => ipcRenderer.invoke("desktop:getVersion"),
  /**
   * 检查 GitHub Releases 更新。
   * @returns {Promise<{ status: string; version?: string; message?: string }>}
   */
  checkForUpdates: () => ipcRenderer.invoke("desktop:checkForUpdates"),
  /**
   * 获取当前自动更新状态。
   * @returns {Promise<{ status: string; currentVersion: string; version?: string; message?: string; percent?: number }>}
   */
  getUpdateState: () => ipcRenderer.invoke("desktop:getUpdateState"),
  /**
   * 退出并安装已下载更新。
   * @returns {Promise<{ ok: boolean; message?: string }>}
   */
  quitAndInstall: () => ipcRenderer.invoke("desktop:quitAndInstall"),
  /**
   * 订阅更新状态推送。
   * @param {(state: { status: string; currentVersion: string; version?: string; message?: string; percent?: number }) => void} callback
   * @returns {() => void} 取消订阅
   */
  onUpdateState: (callback) => {
    const listener = (_event, state) => callback(state);
    ipcRenderer.on("desktop:update-state", listener);
    return () => ipcRenderer.removeListener("desktop:update-state", listener);
  },
  /**
   * 通知主进程生成任务是否进行中（避免强制重启）。
   * @param {boolean} busy
   * @returns {Promise<void>}
   */
  setGenerationBusy: (busy) =>
    ipcRenderer.invoke("desktop:setGenerationBusy", busy),
  /**
   * 用系统默认浏览器打开 http(s) 外链（不在壳内导航）。
   * @param {string} url
   * @returns {Promise<{ ok: boolean, message?: string }>}
   */
  openExternalUrl: (url) => ipcRenderer.invoke("desktop:openExternalUrl", url),
});
