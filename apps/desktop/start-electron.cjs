/**
 * 启动 Electron 桌面壳：先确保二进制，再以本目录为应用根启动。
 */

const { spawn } = require("node:child_process");
const path = require("node:path");
const { ensureElectron } = require("./ensure-electron.cjs");

/**
 * 启动主流程。
 * @returns {Promise<void>}
 */
async function main() {
  const exe = await ensureElectron();
  const child = spawn(exe, ["."], {
    cwd: __dirname,
    stdio: "inherit",
    env: {
      ...process.env,
      // 与 main.cjs / docs/i18n.md 一致：单原点 localhost，避免缓存分裂
      DESKTOP_WEB_URL:
        process.env.DESKTOP_WEB_URL || "http://localhost:5173",
    },
    windowsHide: false,
  });

  /**
   * 将子进程退出码回传给 npm。
   * @param {number|null} code
   * @param {NodeJS.Signals|null} signal
   */
  const forwardExit = (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }
    process.exit(code ?? 0);
  };

  child.on("error", (err) => {
    console.error(`[start-electron] 无法启动 ${exe}:`, err.message);
    process.exit(1);
  });
  child.on("exit", forwardExit);
}

main().catch((err) => {
  console.error(`[start-electron] ${err.message || err}`);
  process.exit(1);
});
