/**
 * 桌面端媒体路径解析：将 API / 相对路径安全映射到 data/ 下本地文件。
 */

const path = require("node:path");

/**
 * 从请求串解析 data/ 下的相对路径；非法或越界返回 null。
 * @param {string} input
 * @returns {string | null} 使用正斜杠的相对路径（自 projects/ 起）
 */
function parseMediaRelativePath(input) {
  if (!input || typeof input !== "string") return null;
  let raw = input.trim().replace(/\\/g, "/");
  if (!raw) return null;

  try {
    if (/^https?:\/\//i.test(raw)) {
      const u = new URL(raw);
      raw = u.pathname || "";
    }
  } catch {
    return null;
  }

  raw = raw.replace(/^\/+/, "");

  const apiMedia = raw.match(
    /^api\/projects\/([^/]+)\/scripts\/([^/]+)\/assets\/(media|exports)\/([^/]+)$/i,
  );
  if (apiMedia) {
    const [, pid, sid, kind, file] = apiMedia;
    return `projects/${pid}/scripts/${sid}/assets/${kind.toLowerCase()}/${decodeURIComponent(file)}`;
  }

  const bareApi = raw.match(
    /^projects\/([^/]+)\/scripts\/([^/]+)\/assets\/(media|exports)\/([^/]+)$/i,
  );
  if (bareApi) {
    const [, pid, sid, kind, file] = bareApi;
    return `projects/${pid}/scripts/${sid}/assets/${kind.toLowerCase()}/${decodeURIComponent(file)}`;
  }

  return null;
}

/**
 * 将相对媒体路径解析为绝对文件路径；必须落在 dataRoot 内。
 * @param {string} input
 * @param {string} dataRoot absolute path to data/
 * @returns {{ absolutePath: string, relativePath: string, name: string } | null}
 */
function resolveLocalMediaPath(input, dataRoot) {
  const relativePath = parseMediaRelativePath(input);
  if (!relativePath) return null;

  const root = path.resolve(dataRoot);
  const absolutePath = path.resolve(root, ...relativePath.split("/"));
  const relToRoot = path.relative(root, absolutePath);
  if (
    !relToRoot ||
    relToRoot.startsWith("..") ||
    path.isAbsolute(relToRoot)
  ) {
    return null;
  }

  return {
    absolutePath,
    relativePath: relativePath,
    name: path.basename(absolutePath),
  };
}

/**
 * 按扩展名猜测 MIME。
 * @param {string} filename
 * @returns {string}
 */
function guessMime(filename) {
  const ext = path.extname(filename).toLowerCase();
  const map = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
  };
  return map[ext] || "application/octet-stream";
}

module.exports = {
  parseMediaRelativePath,
  resolveLocalMediaPath,
  guessMime,
};
