/**
 * 封装 electron-updater：GitHub Releases 检查、后台下载与退出安装。
 */

/** @typedef {'idle'|'checking'|'available'|'not-available'|'downloading'|'downloaded'|'error'|'disabled'} UpdateStatus */

/**
 * @typedef {{
 *   status: UpdateStatus;
 *   currentVersion: string;
 *   version?: string;
 *   message?: string;
 *   percent?: number;
 * }} UpdateState
 */

/**
 * @typedef {{
 *   status: UpdateStatus;
 *   version?: string;
 *   message?: string;
 * }} UpdateCheckResult
 */

/**
 * 合并更新状态补丁。
 * @param {UpdateState} prev
 * @param {Partial<UpdateState>} patch
 * @returns {UpdateState}
 */
function mergeUpdateState(prev, patch) {
  return { ...prev, ...patch };
}

/**
 * 将检查完成后的内部状态映射为 IPC 返回值。
 * @param {UpdateState} state
 * @returns {UpdateCheckResult}
 */
function toCheckResult(state) {
  return {
    status: state.status,
    version: state.version,
    message: state.message,
  };
}

/**
 * 初始化自动更新（仅打包环境启用）。
 * @param {{
 *   app: import("electron").App;
 *   dialog: import("electron").Dialog;
 *   ipcMain: import("electron").IpcMain;
 *   getMainWindow: () => import("electron").BrowserWindow | null;
 * }} deps
 */
function initUpdater({ app, dialog, ipcMain, getMainWindow }) {
  const currentVersion = app.getVersion();

  /** @type {UpdateState} */
  let state = {
    status: "disabled",
    currentVersion,
    message: "开发模式不检查更新",
  };

  let generationBusy = false;
  let pendingInstall = false;
  /** @type {null | (() => void)} */
  let checkResolve = null;
  /** @type {null | ((err: Error) => void)} */
  let checkReject = null;

  /**
   * 向渲染进程广播最新状态。
   */
  function broadcastState() {
    const win = getMainWindow();
    if (!win || win.isDestroyed()) return;
    win.webContents.send("desktop:update-state", getState());
  }

  /**
   * 写入状态并通知前端。
   * @param {Partial<UpdateState>} patch
   */
  function syncState(patch) {
    state = mergeUpdateState(state, patch);
    broadcastState();
  }

  /**
   * 结束一次手动检查 Promise。
   * @param {UpdateCheckResult} result
   */
  function finishCheck(result) {
    if (!checkResolve) return;
    const resolve = checkResolve;
    checkResolve = null;
    checkReject = null;
    resolve(result);
  }

  /**
   * 以错误结束手动检查 Promise。
   * @param {Error} err
   */
  function failCheck(err) {
    const message = err.message || "更新检查失败";
    syncState({ status: "error", message });
    if (checkReject) {
      const reject = checkReject;
      checkResolve = null;
      checkReject = null;
      reject(err);
      return;
    }
    finishCheck({ status: "error", message });
  }

  /**
   * 下载完成后询问是否立即重启（不强制）。
   * @param {string} version
   * @returns {Promise<void>}
   */
  async function promptRestart(version) {
    const win = getMainWindow();
    const result = await dialog.showMessageBox(win ?? undefined, {
      type: "info",
      title: "更新已就绪",
      message: `新版本 ${version} 已下载完成`,
      detail:
        "是否立即重启并安装？选择「稍后」将在退出应用时自动安装。生成任务进行中时不会强制重启。",
      buttons: ["立即重启", "稍后"],
      defaultId: 1,
      cancelId: 1,
      noLink: true,
    });
    if (result.response === 0) {
      tryQuitAndInstall();
    }
  }

  /**
   * 在用户确认后退出并安装；生成进行中时拦截。
   * @returns {{ ok: boolean; message?: string }}
   */
  function tryQuitAndInstall() {
    if (generationBusy) {
      pendingInstall = true;
      const message = "生成任务进行中，请等待完成后再安装更新。";
      void dialog.showMessageBox(getMainWindow() ?? undefined, {
        type: "warning",
        title: "无法立即重启",
        message,
        buttons: ["确定"],
        noLink: true,
      });
      return { ok: false, message };
    }
    pendingInstall = false;
    const { autoUpdater } = require("electron-updater");
    autoUpdater.quitAndInstall(false, true);
    return { ok: true };
  }

  /**
   * 返回当前更新状态快照。
   * @returns {UpdateState}
   */
  function getState() {
    return { ...state };
  }

  /**
   * 手动触发更新检查。
   * @returns {Promise<UpdateCheckResult>}
   */
  async function check() {
    if (!app.isPackaged) {
      return { status: "disabled", message: state.message };
    }
    if (state.status === "checking") {
      return toCheckResult(state);
    }
    if (state.status === "downloaded") {
      return toCheckResult(state);
    }

    const { autoUpdater } = require("electron-updater");

    return new Promise((resolve, reject) => {
      checkResolve = resolve;
      checkReject = reject;
      syncState({ status: "checking", message: "正在检查更新…" });
      autoUpdater.checkForUpdates().catch((err) => {
        failCheck(err instanceof Error ? err : new Error(String(err)));
      });
    });
  }

  if (!app.isPackaged) {
    ipcMain.handle("desktop:checkForUpdates", async () => ({
      status: "disabled",
      message: state.message,
    }));
    ipcMain.handle("desktop:getUpdateState", async () => getState());
    ipcMain.handle("desktop:quitAndInstall", async () => ({
      ok: false,
      message: "开发模式无法安装更新",
    }));
    ipcMain.handle("desktop:setGenerationBusy", async () => undefined);

    return {
      enabled: false,
      getState,
      check,
      quitAndInstall: tryQuitAndInstall,
      setGenerationBusy: () => undefined,
    };
  }

  const { autoUpdater } = require("electron-updater");
  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;

  state = mergeUpdateState(state, {
    status: "idle",
    message: "可从 GitHub Releases 检查更新",
  });

  autoUpdater.on("checking-for-update", () => {
    syncState({ status: "checking", message: "正在检查更新…" });
  });

  autoUpdater.on("update-available", (info) => {
    syncState({
      status: "available",
      version: info.version,
      message: `发现新版本 ${info.version}，正在后台下载…`,
    });
    finishCheck({
      status: "available",
      version: info.version,
      message: `发现新版本 ${info.version}，正在后台下载…`,
    });
  });

  autoUpdater.on("update-not-available", (info) => {
    syncState({
      status: "not-available",
      version: info?.version,
      message: "当前已是最新版本",
    });
    finishCheck({
      status: "not-available",
      version: info?.version,
      message: "当前已是最新版本",
    });
  });

  autoUpdater.on("download-progress", (progress) => {
    const percent = Number(progress.percent) || 0;
    syncState({
      status: "downloading",
      percent,
      message: `正在下载更新 ${Math.round(percent)}%`,
    });
  });

  autoUpdater.on("update-downloaded", (info) => {
    syncState({
      status: "downloaded",
      version: info.version,
      percent: 100,
      message: `新版本 ${info.version} 已下载，可重启安装`,
    });
    finishCheck({
      status: "downloaded",
      version: info.version,
      message: `新版本 ${info.version} 已下载，可重启安装`,
    });
    void promptRestart(info.version);
  });

  autoUpdater.on("error", (err) => {
    failCheck(err instanceof Error ? err : new Error(String(err)));
  });

  ipcMain.handle("desktop:checkForUpdates", async () => {
    try {
      return await check();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return { status: "error", message };
    }
  });

  ipcMain.handle("desktop:getUpdateState", async () => getState());

  ipcMain.handle("desktop:quitAndInstall", async () => tryQuitAndInstall());

  ipcMain.handle("desktop:setGenerationBusy", async (_event, busy) => {
    generationBusy = Boolean(busy);
    if (!generationBusy && pendingInstall) {
      pendingInstall = false;
    }
  });

  return {
    enabled: true,
    getState,
    check,
    quitAndInstall: tryQuitAndInstall,
    /** 标记生成任务是否进行中，避免强制重启。 */
    setGenerationBusy: (busy) => {
      generationBusy = Boolean(busy);
      if (!generationBusy && pendingInstall) {
        pendingInstall = false;
      }
    },
  };
}

module.exports = {
  initUpdater,
  mergeUpdateState,
  toCheckResult,
};
