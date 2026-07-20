/**
 * 桌面应用用户数据目录解析（data / logs / .env 根路径）。
 */

const path = require("node:path");

/**
 * 解析用户数据根目录；支持 SVG_USER_DATA_ROOT 覆盖。
 * @param {NodeJS.ProcessEnv} env
 * @param {NodeJS.Platform} platform
 * @param {string} homedir
 * @param {string} localAppData Windows LOCALAPPDATA，其他平台可传空串
 * @returns {string}
 */
function resolveUserDataRoot(env, platform, homedir, localAppData) {
  const override = (env.SVG_USER_DATA_ROOT || "").trim();
  if (override) {
    return path.resolve(override);
  }
  if (platform === "win32") {
    const base = localAppData || path.join(homedir, "AppData", "Local");
    return path.join(base, "SuperVideoGenerator");
  }
  if (platform === "darwin") {
    return path.join(
      homedir,
      "Library",
      "Application Support",
      "SuperVideoGenerator",
    );
  }
  return path.join(homedir, ".local", "share", "SuperVideoGenerator");
}

module.exports = {
  resolveUserDataRoot,
};
