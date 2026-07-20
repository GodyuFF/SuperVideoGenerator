/**
 * Electron 主进程：无菜单栏窗口 + 自动拉起 API/Vite + 加载前端。
 */

const { app, BrowserWindow, Menu, ipcMain } = require("electron");
const fs = require("node:fs/promises");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const {
  resolveLocalMediaPath,
  guessMime,
} = require("./mediaPath.cjs");
const { ensureDevServers } = require("./devServers.cjs");

/** 仓库根目录（apps/desktop 的上两级）。 */
const REPO_ROOT = path.resolve(__dirname, "..", "..");

/** 圆软小夜枭品牌标（Windows 任务栏 / 窗口图标）。 */
const APP_ICON = path.join(__dirname, "icon.ico");

// Windows 任务栏分组与自定义图标稳定关联
if (process.platform === "win32") {
  app.setAppUserModelId("com.supervideogenerator.desktop");
}
/**
 * 解析 data 根目录。
 * @returns {string}
 */
function resolveDataRoot() {
  const fromEnv = process.env.SVG_DATA_ROOT || process.env.DESKTOP_DATA_ROOT;
  if (fromEnv && fromEnv.trim()) {
    return path.resolve(fromEnv.trim());
  }
  return path.join(REPO_ROOT, "data");
}

const DATA_ROOT = resolveDataRoot();
const WEB_URL =
  process.env.DESKTOP_WEB_URL || "http://localhost:5173";

/** 桌面冷启动胶片动画页（与 Web 启动页视觉一致）。 */
const SPLASH_BOOT_HTML = path.join(__dirname, "splash-boot.html");

/** @type {null | { stop: () => void, logPath?: string }} */
let managedServers = null;

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

  win.once("ready-to-show", reveal);
  setTimeout(reveal, 800);

  win.webContents.on(
    "did-fail-load",
    (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
      if (!isMainFrame) return;
      console.error(
        `[desktop] load failed code=${errorCode} url=${validatedURL}: ${errorDescription}`,
      );
      reveal();
      setTimeout(() => {
        if (!win.isDestroyed()) void win.loadURL(WEB_URL);
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

  ipcMain.handle("desktop:getInfo", async () => ({
    isDesktop: true,
    dataRoot: DATA_ROOT,
    webUrl: WEB_URL,
    repoRoot: REPO_ROOT,
  }));
}

/**
 * 应用启动：先建窗显示状态，服务就绪后再进前端。
 * @returns {Promise<void>}
 */
async function boot() {
  registerMediaIpc();
  const win = createWindow();
  void win.loadFile(SPLASH_BOOT_HTML);

  try {
    managedServers = await ensureDevServers(REPO_ROOT, { webUrl: WEB_URL });
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
    console.log(`[desktop] loadURL ${WEB_URL}`);
    void win.loadURL(WEB_URL);
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
