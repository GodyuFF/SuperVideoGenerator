/**
 * 桌面壳本地开发服编排：探测并按需拉起 FastAPI / Vite（无控制台窗口）。
 */

const { spawn } = require("node:child_process");
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

/** @typedef {{ kill: () => void, pid?: number }} ManagedChild */

/**
 * 解析桌面启动日志路径。
 * @returns {string}
 */
function resolveDesktopLogPath() {
  const base =
    process.env.LOCALAPPDATA ||
    path.join(os.homedir(), "AppData", "Local");
  const dir = path.join(base, "SuperVideoGenerator", "logs");
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, "desktop-servers.log");
}

/**
 * 追加一行日志。
 * @param {string} line
 */
function appendLog(line) {
  try {
    fs.appendFileSync(
      resolveDesktopLogPath(),
      `[${new Date().toISOString()}] ${line}\n`,
      "utf8",
    );
  } catch {
    /* 日志失败不阻断启动 */
  }
}

/**
 * 发起一次 HTTP GET，成功返回 true。
 * @param {string} url
 * @param {number} timeoutMs
 * @returns {Promise<boolean>}
 */
function probeUrl(url, timeoutMs = 1500) {
  return new Promise((resolve) => {
    let settled = false;
    /** 结束探测。 */
    const done = (ok) => {
      if (settled) return;
      settled = true;
      resolve(ok);
    };
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      res.resume();
      done((res.statusCode ?? 500) < 500);
    });
    req.on("timeout", () => {
      req.destroy();
      done(false);
    });
    req.on("error", () => done(false));
  });
}

/**
 * 轮询多个候选 URL，任一就绪即成功。
 * @param {string[]} urls
 * @param {number} timeoutMs
 * @param {number} intervalMs
 * @returns {Promise<boolean>}
 */
async function waitForAnyUrl(urls, timeoutMs = 90_000, intervalMs = 500) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    for (const url of urls) {
      if (await probeUrl(url)) return true;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  for (const url of urls) {
    if (await probeUrl(url)) return true;
  }
  return false;
}

/**
 * 在 Windows 上静默启动子进程（不弹黑框）；.cmd 走 cmd /c 以保证能跑起来。
 * @param {string} command
 * @param {string[]} args
 * @param {{ cwd: string, env?: NodeJS.ProcessEnv, label?: string }} opts
 * @returns {ManagedChild}
 */
function spawnHidden(command, args, opts) {
  const label = opts.label || command;
  const isWin = process.platform === "win32";
  const needsCmd =
    isWin &&
    (/\.cmd$/i.test(command) ||
      /\.bat$/i.test(command) ||
      command === "npm" ||
      command === "npm.cmd");

  /** @type {import('node:child_process').ChildProcessWithoutNullStreams | import('node:child_process').ChildProcess} */
  let child;
  if (needsCmd) {
    const line = [command, ...args]
      .map((p) => (/\s/.test(p) ? `"${p}"` : p))
      .join(" ");
    child = spawn("cmd.exe", ["/d", "/s", "/c", line], {
      cwd: opts.cwd,
      env: opts.env ? { ...process.env, ...opts.env } : process.env,
      stdio: "ignore",
      windowsHide: true,
      detached: false,
      shell: false,
    });
  } else {
    child = spawn(command, args, {
      cwd: opts.cwd,
      env: opts.env ? { ...process.env, ...opts.env } : process.env,
      stdio: "ignore",
      windowsHide: true,
      detached: false,
      shell: false,
    });
  }

  child.on("error", (err) => {
    appendLog(`${label} spawn error: ${err.message}`);
  });
  child.on("exit", (code, signal) => {
    appendLog(`${label} exited code=${code} signal=${signal}`);
  });
  appendLog(`${label} spawned pid=${child.pid} cwd=${opts.cwd}`);

  let killed = false;
  return {
    pid: child.pid,
    /** 结束该子进程（Windows 用 taskkill 树杀，避免孤儿 npm）。 */
    kill() {
      if (killed) return;
      killed = true;
      if (child.killed || child.exitCode != null) return;
      try {
        if (isWin && child.pid) {
          spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
            stdio: "ignore",
            windowsHide: true,
          });
        } else {
          child.kill("SIGTERM");
        }
      } catch {
        /* 退出阶段杀进程失败可忽略 */
      }
    },
  };
}

/**
 * 解析仓库内 Python / npm 可执行文件路径。
 * @param {string} repoRoot
 * @returns {{ python: string, npm: string }}
 */
function resolveTooling(repoRoot) {
  const pythonWin = path.join(repoRoot, ".venv", "Scripts", "python.exe");
  const pythonUnix = path.join(repoRoot, ".venv", "bin", "python");
  const python = fs.existsSync(pythonWin)
    ? pythonWin
    : fs.existsSync(pythonUnix)
      ? pythonUnix
      : "";
  const npm = process.platform === "win32" ? "npm.cmd" : "npm";
  return { python, npm };
}

/**
 * Vite 探测候选地址（IPv4 / localhost）。
 * @param {string} webUrl
 * @returns {string[]}
 */
function viteProbeUrls(webUrl) {
  const urls = [webUrl];
  if (webUrl.includes("localhost")) {
    urls.push(webUrl.replace("localhost", "127.0.0.1"));
  } else if (webUrl.includes("127.0.0.1")) {
    urls.push(webUrl.replace("127.0.0.1", "localhost"));
  }
  return [...new Set(urls)];
}

/**
 * 确保 API + Vite 可用；返回退出时清理句柄。
 * @param {string} repoRoot
 * @param {{ webUrl?: string, apiProbeUrl?: string, skip?: boolean }} [options]
 * @returns {Promise<{ stop: () => void, apiReady: boolean, webReady: boolean, logPath: string }>}
 */
async function ensureDevServers(repoRoot, options = {}) {
  const logPath = resolveDesktopLogPath();
  appendLog(`ensureDevServers repo=${repoRoot}`);

  const skip =
    options.skip ||
    process.env.SVG_DESKTOP_SKIP_SERVERS === "1" ||
    process.env.SVG_DESKTOP_SKIP_SERVERS === "true";
  const webUrl = options.webUrl || "http://localhost:5173";
  const apiProbeUrl =
    options.apiProbeUrl || "http://127.0.0.1:8000/api/edit/capabilities";
  const webProbes = viteProbeUrls(webUrl);

  /** @type {ManagedChild[]} */
  const owned = [];

  if (skip) {
    const apiReady = await waitForAnyUrl([apiProbeUrl], 5_000);
    const webReady = await waitForAnyUrl(webProbes, 5_000);
    return { apiReady, webReady, logPath, stop() {} };
  }

  let apiReady = await probeUrl(apiProbeUrl);
  if (!apiReady) {
    const { python } = resolveTooling(repoRoot);
    if (!python) {
      throw new Error("未找到 .venv Python，无法启动 API");
    }
    appendLog("starting API on :8000");
    owned.push(
      spawnHidden(
        python,
        ["-m", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"],
        { cwd: repoRoot, label: "api" },
      ),
    );
    apiReady = await waitForAnyUrl([apiProbeUrl], 90_000);
    appendLog(`apiReady=${apiReady}`);
  }

  let webReady = await waitForAnyUrl(webProbes, 1_000);
  if (!webReady) {
    const { npm } = resolveTooling(repoRoot);
    appendLog("starting Vite on :5173");
    owned.push(
      spawnHidden(npm, ["run", "dev"], {
        cwd: path.join(repoRoot, "apps", "web"),
        env: { BROWSER: "none" },
        label: "vite",
      }),
    );
    webReady = await waitForAnyUrl(webProbes, 90_000);
    appendLog(`webReady=${webReady}`);
  }

  return {
    apiReady,
    webReady,
    logPath,
    /** 仅终止本进程拉起的子服务。 */
    stop() {
      for (const c of owned) c.kill();
      owned.length = 0;
    },
  };
}

module.exports = {
  probeUrl,
  waitForAnyUrl,
  ensureDevServers,
  resolveTooling,
  viteProbeUrls,
  resolveDesktopLogPath,
};
