/**
 * Electron 主进程：无菜单栏窗口 + 自动拉起 API/Vite + 加载前端。
 */

const { app, BrowserWindow, Menu, ipcMain, dialog, shell } = require("electron");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const {
  resolveLocalMediaPath,
  guessMime,
} = require("./mediaPath.cjs");
const { ensureDevServers } = require("./devServers.cjs");
const { resolveUserDataRoot } = require("./userDataPaths.cjs");
const { ensureProdApi, resolveRuntimeRoot } = require("./prodServers.cjs");
const { initUpdater } = require("./updater.cjs");
const { isAllowedExternalUrl } = require("./openExternal.cjs");

/** 仓库根目录（apps/desktop 的上两级）。 */
const REPO_ROOT = path.resolve(__dirname, "..", "..");

/** 圆软小夜枭品牌标（Windows 任务栏 / 窗口图标）。 */
const APP_ICON = path.join(__dirname, "icon.ico");

// Windows 任务栏分组与自定义图标稳定关联
if (process.platform === "win32") {
  app.setAppUserModelId("com.supervideogenerator.desktop");
}
/** 用户数据根目录（logs、.env、默认 data 父路径）。 */
const USER_DATA_ROOT = resolveUserDataRoot(
  process.env,
  process.platform,
  os.homedir(),
  process.env.LOCALAPPDATA || "",
);

/**
 * 解析 data 根目录。
 * @returns {string}
 */
function resolveDataRoot() {
  const fromEnv = process.env.SVG_DATA_ROOT || process.env.DESKTOP_DATA_ROOT;
  if (fromEnv && fromEnv.trim()) {
    return path.resolve(fromEnv.trim());
  }
  if (app.isPackaged) {
    return path.join(USER_DATA_ROOT, "data");
  }
  return path.join(REPO_ROOT, "data");
}

const DATA_ROOT = resolveDataRoot();
const DEV_WEB_URL =
  process.env.DESKTOP_WEB_URL || "http://localhost:5173";
const PACKAGED_WEB_URL = "http://127.0.0.1:8000/";

/**
 * 当前运行模式下的前端入口 URL。
 * @returns {string}
 */
function getActiveWebUrl() {
  return app.isPackaged ? PACKAGED_WEB_URL : DEV_WEB_URL;
}

/** 桌面冷启动胶片动画页（与 Web 启动页视觉一致）。 */
const SPLASH_BOOT_HTML = path.join(__dirname, "splash-boot.html");

/** @type {null | { stop: () => void, logPath?: string }} */
let managedServers = null;

/** @type {BrowserWindow | null} */
let mainWindow = null;

/**
 * 生成启动失败页 HTML。
 * @param {string} [detail]
 * @returns {string}
 */
function errorPageHtml(detail = "") {
  const title = "启动失败";
  const body = `无法加载界面。<br/><br/>${detail.replace(/</g, "&lt;")}`;
  return `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<title>SuperVideoGenerator</title>
<style>
  html,body{height:100%;margin:0;background:#0b0e14;color:#e6eaf2;
  font-family:Segoe UI,"PingFang SC","Microsoft YaHei",sans-serif;}
  main{min-height:100%;display:flex;align-items:center;justify-content:center;
  padding:2rem;text-align:center;line-height:1.6;}
  h1{font-size:1.25rem;font-weight:600;margin:0 0 .75rem;
  font-family:Georgia,"Newsreader",serif;}
  p{margin:0;opacity:.85;max-width:36rem;}
  code{font-size:.85rem;opacity:.7;word-break:break-all;}
</style></head>
<body><main><div><h1>${title}</h1><p>${body}</p></div></main></body></html>`;
}

/**
 * 用系统默认浏览器打开外链。
 * @param {string} url
 * @returns {Promise<{ ok: boolean, message?: string }>}
 */
async function openExternalUrl(url) {
  if (!isAllowedExternalUrl(url)) {
    return { ok: false, message: "仅支持 http(s) 外链" };
  }
  try {
    await shell.openExternal(url);
    return { ok: true };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, message };
  }
}

/**
 * 创建无菜单栏主窗口。
 * @returns {BrowserWindow}
 */
function createWindow() {
  // 去掉 File / Edit / View 等默认菜单，避免像“半成品浏览器”
  Menu.setApplicationMenu(null);

  const iconPath = APP_ICON;
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    show: false,
    title: "SuperVideoGenerator",
    icon: iconPath,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  /** 确保窗口可见。 */
  const reveal = () => {
    if (!win.isDestroyed() && !win.isVisible()) win.show();
  };

  mainWindow = win;
  win.on("closed", () => {
    if (mainWindow === win) {
      mainWindow = null;
    }
  });

  win.once("ready-to-show", reveal);
  setTimeout(reveal, 800);

  // target=_blank / window.open → 系统浏览器，禁止在壳内新开窗口
  win.webContents.setWindowOpenHandler(({ url }) => {
    void openExternalUrl(url);
    return { action: "deny" };
  });

  win.webContents.on(
    "did-fail-load",
    (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
      if (!isMainFrame) return;
      console.error(
        `[desktop] load failed code=${errorCode} url=${validatedURL}: ${errorDescription}`,
      );
      reveal();
      setTimeout(() => {
        if (!win.isDestroyed()) void win.loadURL(getActiveWebUrl());
      }, 1500);
    },
  );

  return win;
}

/**
 * 注册本地媒体读取 IPC。
 */
function registerMediaIpc() {
  ipcMain.handle("media:readLocal", async (_event, input) => {
    const resolved = resolveLocalMediaPath(String(input || ""), DATA_ROOT);
    if (!resolved) {
      throw new Error("非法或不受支持的媒体路径");
    }
    let buf;
    try {
      buf = await fs.readFile(resolved.absolutePath);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      throw new Error(`读取本地媒体失败: ${message}`);
    }
    return {
      name: resolved.name,
      mime: guessMime(resolved.name),
      data: buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength),
      absolutePath: resolved.absolutePath,
      fileUrl: pathToFileURL(resolved.absolutePath).href,
    };
  });

  ipcMain.handle("desktop:getVersion", async () => app.getVersion());

  ipcMain.handle("desktop:getInfo", async () => ({
    isDesktop: true,
    packaged: app.isPackaged,
    dataRoot: DATA_ROOT,
    webUrl: getActiveWebUrl(),
    repoRoot: app.isPackaged ? "" : REPO_ROOT,
    appVersion: app.getVersion(),
  }));

  ipcMain.handle("desktop:openExternalUrl", async (_event, url) =>
    openExternalUrl(String(url || "")),
  );
}

/**
 * 应用启动：先建窗显示状态，服务就绪后再进前端。
 * @returns {Promise<void>}
 */
async function boot() {
  registerMediaIpc();
  initUpdater({
    app,
    dialog,
    ipcMain,
    getMainWindow: () => mainWindow,
  });
  const win = createWindow();
  void win.loadFile(SPLASH_BOOT_HTML);

  try {
    if (app.isPackaged) {
      const runtimeRoot = resolveRuntimeRoot(process.resourcesPath);
      managedServers = await ensureProdApi(runtimeRoot, USER_DATA_ROOT);
      const url = PACKAGED_WEB_URL;
      if (!managedServers.apiReady) {
        const logHint = managedServers.logPath
          ? `<br/><br/><code>${managedServers.logPath}</code>`
          : "";
        void win.loadURL(
          `data:text/html;charset=utf-8,${encodeURIComponent(
            errorPageHtml(
              `本地 API（:8000）未就绪。请查看日志或重启应用。${logHint}`,
            ),
          )}`,
        );
        return;
      }
      console.log(`[desktop] loadURL ${url}`);
      void win.loadURL(url);
      return;
    }

    managedServers = await ensureDevServers(REPO_ROOT, { webUrl: DEV_WEB_URL });
    if (!managedServers.webReady) {
      const logHint = managedServers.logPath
        ? `<br/><br/><code>${managedServers.logPath}</code>`
        : "";
      void win.loadURL(
        `data:text/html;charset=utf-8,${encodeURIComponent(
          errorPageHtml(
            `本地前端（Vite :5173）未就绪。请确认已安装 Node 依赖（apps/web），或查看日志。${logHint}`,
          ),
        )}`,
      );
      return;
    }
    console.log(`[desktop] loadURL ${DEV_WEB_URL}`);
    void win.loadURL(DEV_WEB_URL);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`[desktop] 启动失败: ${message}`);
    void win.loadURL(
      `data:text/html;charset=utf-8,${encodeURIComponent(
        errorPageHtml(message),
      )}`,
    );
  }
}

app.whenReady().then(() => {
  void boot();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      void boot();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("will-quit", () => {
  if (managedServers) {
    managedServers.stop();
    managedServers = null;
  }
});
