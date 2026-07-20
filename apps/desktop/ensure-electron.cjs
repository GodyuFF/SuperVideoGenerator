/**
 * 确保本机已有可用的 Electron 二进制（安装到 LocalAppData，避开工作区文件锁）。
 * 中国大陆默认走 npmmirror；可通过 ELECTRON_MIRROR 覆盖。
 */

const fs = require("node:fs");
const fsp = require("node:fs/promises");
const https = require("node:https");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const DEFAULT_MIRROR = "https://npmmirror.com/mirrors/electron/";

/**
 * 读取本包声明的 Electron 版本号。
 * @returns {string}
 */
function readElectronVersion() {
  const pkg = JSON.parse(
    fs.readFileSync(path.join(__dirname, "package.json"), "utf8"),
  );
  const raw = pkg.devDependencies?.electron || pkg.dependencies?.electron;
  if (!raw || typeof raw !== "string") {
    throw new Error("package.json 未声明 electron 依赖版本");
  }
  return raw.replace(/^[\^~>=\s]+/, "");
}

/**
 * 解析二进制安装根目录（工作区外，避免 Cursor/索引锁住 asar）。
 * @param {string} version
 * @returns {string}
 */
function resolveInstallRoot(version) {
  const base =
    process.env.SVG_ELECTRON_HOME ||
    path.join(
      process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local"),
      "SuperVideoGenerator",
      "electron",
    );
  return path.join(base, `v${version}`);
}

/**
 * 解析 electron.exe 期望路径。
 * @param {string} version
 * @returns {string}
 */
function resolveElectronExe(version) {
  return path.join(resolveInstallRoot(version), "electron.exe");
}

/**
 * 判断指定版本的 Electron 是否已安装完整。
 * @param {string} version
 * @returns {boolean}
 */
function isElectronReady(version) {
  const exe = resolveElectronExe(version);
  if (!fs.existsSync(exe)) return false;
  const versionFile = path.join(resolveInstallRoot(version), "version");
  if (!fs.existsSync(versionFile)) return true;
  try {
    const got = fs.readFileSync(versionFile, "utf8").replace(/^v/, "").trim();
    return got === version;
  } catch {
    return true;
  }
}

/**
 * 拼接镜像下载 URL。
 * @param {string} version
 * @returns {string}
 */
function buildDownloadUrl(version) {
  const mirror = (process.env.ELECTRON_MIRROR || DEFAULT_MIRROR).replace(
    /\/?$/,
    "/",
  );
  const platform = process.env.npm_config_platform || process.platform;
  const arch = process.env.npm_config_arch || process.arch;
  return `${mirror}v${version}/electron-v${version}-${platform}-${arch}.zip`;
}

/**
 * 将远程文件下载到本地路径。
 * @param {string} url
 * @param {string} destPath
 * @returns {Promise<void>}
 */
function downloadFile(url, destPath) {
  return new Promise((resolve, reject) => {
    const client = url.startsWith("https:") ? https : http;
    const file = fs.createWriteStream(destPath);
    const req = client.get(url, { timeout: 120_000 }, (res) => {
      if (
        res.statusCode &&
        res.statusCode >= 300 &&
        res.statusCode < 400 &&
        res.headers.location
      ) {
        file.close();
        fs.unlink(destPath, () => {});
        downloadFile(res.headers.location, destPath).then(resolve).catch(reject);
        return;
      }
      if (res.statusCode !== 200) {
        file.close();
        fs.unlink(destPath, () => {});
        reject(new Error(`下载失败 HTTP ${res.statusCode}: ${url}`));
        return;
      }
      res.pipe(file);
      file.on("finish", () => file.close(() => resolve()));
    });
    req.on("timeout", () => {
      req.destroy(new Error(`下载超时: ${url}`));
    });
    req.on("error", (err) => {
      file.close();
      fs.unlink(destPath, () => {});
      reject(err);
    });
  });
}

/**
 * 用 PowerShell Expand-Archive 解压 zip（不依赖 extract-zip / 工作区 node_modules）。
 * @param {string} zipPath
 * @param {string} destDir
 */
function extractZip(zipPath, destDir) {
  const ps = `
$ErrorActionPreference = 'Stop'
Expand-Archive -LiteralPath '${zipPath.replace(/'/g, "''")}' -DestinationPath '${destDir.replace(/'/g, "''")}' -Force
`;
  const result = spawnSync(
    "powershell.exe",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
    { encoding: "utf8" },
  );
  if (result.status !== 0) {
    throw new Error(
      `解压 Electron 失败: ${result.stderr || result.stdout || result.status}`,
    );
  }
}

/**
 * 下载并安装 Electron 到 LocalAppData。
 * @param {string} version
 * @returns {Promise<string>} electron.exe 绝对路径
 */
async function installElectron(version) {
  const root = resolveInstallRoot(version);
  await fsp.mkdir(root, { recursive: true });
  const url = buildDownloadUrl(version);
  const zipPath = path.join(
    os.tmpdir(),
    `svf-electron-v${version}-${process.platform}-${process.arch}.zip`,
  );
  console.log(`[ensure-electron] 下载 ${url}`);
  await downloadFile(url, zipPath);
  console.log(`[ensure-electron] 解压到 ${root}`);
  extractZip(zipPath, root);
  try {
    await fsp.unlink(zipPath);
  } catch {
    /* 临时 zip 删除失败可忽略 */
  }
  const exe = resolveElectronExe(version);
  if (!fs.existsSync(exe)) {
    throw new Error(`解压后未找到 electron.exe: ${exe}`);
  }
  await fsp.writeFile(path.join(root, "version"), version, "utf8");
  return exe;
}

/**
 * 确保 Electron 可用并返回可执行文件路径。
 * @returns {Promise<string>}
 */
async function ensureElectron() {
  const version = readElectronVersion();
  if (isElectronReady(version)) {
    return resolveElectronExe(version);
  }
  return installElectron(version);
}

module.exports = {
  readElectronVersion,
  resolveInstallRoot,
  resolveElectronExe,
  isElectronReady,
  buildDownloadUrl,
  ensureElectron,
};

if (require.main === module) {
  ensureElectron()
    .then((exe) => {
      console.log(`[ensure-electron] 就绪: ${exe}`);
      process.exit(0);
    })
    .catch((err) => {
      console.error(`[ensure-electron] 失败: ${err.message || err}`);
      process.exit(1);
    });
}
