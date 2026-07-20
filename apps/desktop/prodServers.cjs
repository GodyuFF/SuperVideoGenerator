/**
 * 打包模式：用嵌入式 Python 启动 API（托管静态前端）。
 */

const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");
const { spawnHidden } = require("./devServers.cjs");

const API_PROBE_URL = "http://127.0.0.1:8000/health";
const WEB_URL = "http://127.0.0.1:8000/";
const API_PORT = 8000;
const API_HOST = "127.0.0.1";

/**
 * 判断 HTTP 状态码是否为 /health 成功响应（2xx）。
 * @param {number | undefined} statusCode
 * @returns {boolean}
 */
function isHealthStatusOk(statusCode) {
  const code = statusCode ?? 500;
  return code >= 200 && code < 300;
}

/**
 * 判断 /health JSON 响应体是否包含 status ok。
 * @param {string} body
 * @returns {boolean}
 */
function isHealthBodyOk(body) {
  return /"status"\s*:\s*"ok"/.test(body);
}

/**
 * GET /health，仅 2xx 且 body 含 status ok 时视为 SuperVideoGenerator API 就绪。
 * @param {string} url
 * @param {number} timeoutMs
 * @returns {Promise<boolean>}
 */
function probeHealthOk(url, timeoutMs = 1500) {
  return new Promise((resolve) => {
    let settled = false;
    /** 结束探测并返回是否健康。 */
    const done = (ok) => {
      if (settled) return;
      settled = true;
      resolve(ok);
    };
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      const chunks = [];
      res.on("data", (chunk) => chunks.push(chunk));
      res.on("end", () => {
        const body = Buffer.concat(chunks).toString("utf8");
        done(isHealthStatusOk(res.statusCode) && isHealthBodyOk(body));
      });
      res.on("error", () => done(false));
    });
    req.on("timeout", () => {
      req.destroy();
      done(false);
    });
    req.on("error", () => done(false));
  });
}

/**
 * 轮询直到 /health 返回 2xx 且 status ok。
 * @param {string} url
 * @param {number} timeoutMs
 * @param {number} intervalMs
 * @returns {Promise<boolean>}
 */
async function waitForHealthOk(url, timeoutMs = 90_000, intervalMs = 500) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await probeHealthOk(url)) return true;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return probeHealthOk(url);
}

/**
 * 解析打包资源内 runtime 目录。
 * @param {string} resourcesPath Electron process.resourcesPath
 * @returns {string}
 */
function resolveRuntimeRoot(resourcesPath) {
  return path.join(resourcesPath, "runtime");
}

/**
 * 解析嵌入式 Python 可执行文件路径。
 * @param {string} runtimeRoot
 * @param {NodeJS.Platform} platform
 * @returns {string}
 */
function resolveEmbeddedPython(runtimeRoot, platform) {
  if (platform === "win32") {
    return path.join(runtimeRoot, "python", "python.exe");
  }
  return path.join(runtimeRoot, "python", "bin", "python3");
}

/**
 * 检测本地 TCP 端口是否已有进程监听。
 * @param {number} port
 * @param {string} host
 * @returns {Promise<boolean>}
 */
function isPortOpen(port, host = API_HOST) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ port, host });
    /** 结束探测并返回端口是否已占用。 */
    const finish = (open) => {
      socket.removeAllListeners();
      try {
        socket.destroy();
      } catch {
        /* 忽略关闭错误 */
      }
      resolve(open);
    };
    socket.setTimeout(500);
    socket.on("connect", () => finish(true));
    socket.on("timeout", () => finish(false));
    socket.on("error", () => finish(false));
  });
}

/**
 * 追加一行到用户数据目录下的桌面服务日志。
 * @param {string} logPath
 * @param {string} line
 */
function appendLog(logPath, line) {
  try {
    fs.appendFileSync(
      logPath,
      `[${new Date().toISOString()}] ${line}\n`,
      "utf8",
    );
  } catch {
    /* 日志失败不阻断启动 */
  }
}

/**
 * 打包模式拉起嵌入式 API；端口已占用且 /health 可用时复用外部实例。
 * @param {string} runtimeRoot
 * @param {string} userDataRoot
 * @param {{ skip?: boolean }} [options]
 * @returns {Promise<{ stop: () => void, apiReady: boolean, logPath: string, webUrl: string }>}
 */
async function ensureProdApi(runtimeRoot, userDataRoot, options = {}) {
  const logsDir = path.join(userDataRoot, "logs");
  const dataRoot = path.join(userDataRoot, "data");
  fs.mkdirSync(dataRoot, { recursive: true });
  fs.mkdirSync(logsDir, { recursive: true });

  const logPath = path.join(logsDir, "desktop-servers.log");
  const webUrl = WEB_URL;

  const skip =
    options.skip ||
    process.env.SVG_DESKTOP_SKIP_SERVERS === "1" ||
    process.env.SVG_DESKTOP_SKIP_SERVERS === "true";

  appendLog(logPath, `ensureProdApi runtime=${runtimeRoot} userData=${userDataRoot}`);

  if (skip) {
    const apiReady = await waitForHealthOk(API_PROBE_URL, 5_000);
    appendLog(logPath, `skip mode apiReady=${apiReady}`);
    return { apiReady, logPath, webUrl, stop() {} };
  }

  if (await probeHealthOk(API_PROBE_URL)) {
    appendLog(logPath, "reusing existing API on :8000");
    return { apiReady: true, logPath, webUrl, stop() {} };
  }

  if (await isPortOpen(API_PORT)) {
    throw new Error(
      "端口 8000 已被占用，且 /health 不可用；请关闭占用进程后重试",
    );
  }

  const python = resolveEmbeddedPython(runtimeRoot, process.platform);
  const webRoot = path.join(runtimeRoot, "web");
  const boot = path.join(runtimeRoot, "api_boot.py");
  const srcRoot = path.join(runtimeRoot, "src");

  const env = {
    ...process.env,
    SVG_DATA_ROOT: dataRoot,
    SVG_DESKTOP_WEB_ROOT: webRoot,
    SVG_DESKTOP_PACKAGED: "1",
    PYTHONPATH: srcRoot,
  };

  appendLog(logPath, `starting packaged API python=${python} boot=${boot}`);
  const child = spawnHidden(python, [boot], {
    cwd: runtimeRoot,
    env,
    label: "prod-api",
  });

  const apiReady = await waitForHealthOk(API_PROBE_URL, 90_000);
  appendLog(logPath, `apiReady=${apiReady}`);

  return {
    apiReady,
    logPath,
    webUrl,
    /** 仅终止本进程拉起的嵌入式 API。 */
    stop() {
      child.kill();
    },
  };
}

module.exports = {
  resolveRuntimeRoot,
  resolveEmbeddedPython,
  ensureProdApi,
  isHealthStatusOk,
  isHealthBodyOk,
  API_PROBE_URL,
  WEB_URL,
};
