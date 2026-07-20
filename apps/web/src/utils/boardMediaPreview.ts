/**
 * 从看板条目解析可展示的媒体预览 URL。
 * 注意：board item.preview 常为摘要文案，不可直接当作 img src。
 */

const IMAGE_EXT_RE = /\.(png|jpe?g|webp|gif|bmp|avif|svg)(\?|#|$)/i;
const VIDEO_EXT_RE = /\.(mp4|webm|mov|m4v)(\?|#|$)/i;

/** 规范化路径分隔符并去首尾空白。 */
function normalizeMediaCandidate(raw: string | undefined | null): string {
  return String(raw ?? "").trim().replace(/\\/g, "/");
}

/** 字符串是否像可请求的媒体路径/URL（排除中文摘要等文案）。 */
export function looksLikeMediaUrl(raw: string | undefined | null): boolean {
  const u = normalizeMediaCandidate(raw);
  if (!u) return false;
  if (u.startsWith("http://") || u.startsWith("https://") || u.startsWith("/api/")) {
    return true;
  }
  if (u.startsWith("file:")) return true;
  if (/^[A-Za-z]:\//.test(u)) return true;
  if (/^projects\/[^/]+\/scripts\/[^/]+\/assets\/(media|exports)\//.test(u)) {
    return true;
  }
  if (IMAGE_EXT_RE.test(u) || VIDEO_EXT_RE.test(u)) return true;
  // 纯文件名（无空白、无 CJK）
  if (!/[\s\u4e00-\u9fff]/.test(u) && u.includes(".") && !u.includes("/")) {
    return true;
  }
  return false;
}

/** 是否像静态图片 URL（可用于 <img>，排除视频扩展名）。 */
export function looksLikeImageUrl(raw: string | undefined | null): boolean {
  const u = normalizeMediaCandidate(raw);
  if (!u || !looksLikeMediaUrl(u)) return false;
  if (VIDEO_EXT_RE.test(u)) return false;
  if (IMAGE_EXT_RE.test(u)) return true;
  // 无扩展名的 /api/ 媒体路径：按图片尝试，加载失败由预览组件回退
  return true;
}

/** 是否像视频文件 URL（应用 <video> 而非 <img>）。 */
export function looksLikeVideoUrl(raw: string | undefined | null): boolean {
  const u = normalizeMediaCandidate(raw);
  if (!u || !looksLikeMediaUrl(u)) return false;
  return VIDEO_EXT_RE.test(u);
}

/** 从看板条目收集候选媒体 URL，返回首个可用者。 */
export function pickBoardMediaPreviewUrl(item: Record<string, unknown>): string {
  const candidates: string[] = [];
  const push = (v: unknown) => {
    const s = String(v ?? "").trim();
    if (s) candidates.push(s);
  };

  push(item.preview_url);
  for (const key of ["images", "media", "videos"] as const) {
    const list = Array.isArray(item[key]) ? item[key] : [];
    for (const row of list) {
      if (!row || typeof row !== "object") continue;
      const m = row as { url?: unknown; link?: unknown; type?: unknown };
      push(m.link);
      push(m.url);
    }
  }
  // preview 仅在像媒体路径时采用（frame 看板里多为中文摘要）
  push(item.preview);

  for (const c of candidates) {
    if (looksLikeMediaUrl(c)) return c;
  }
  return "";
}
