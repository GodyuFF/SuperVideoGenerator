/**
 * 将 MediaAsset.url（相对 data/ 路径或 API 路径）转为可播放/预览的 URL。
 */

export function isTimelinePlaceholderUrl(url: string | undefined): boolean {
  return Boolean(url?.trim().toLowerCase().startsWith("timeline://"));
}

export function resolveMediaPlayUrl(
  url: string | undefined,
  projectId?: string | null,
  scriptId?: string | null
): string {
  if (!url?.trim()) return "";
  const u = url.trim().replace(/\\/g, "/");
  if (isTimelinePlaceholderUrl(u)) return "";
  if (u.startsWith("http://") || u.startsWith("https://")) return u;
  if (u.startsWith("/api/")) return u;

  const mediaRelMatch = u.match(
    /^projects\/([^/]+)\/scripts\/([^/]+)\/assets\/media\/([^/]+)$/
  );
  if (mediaRelMatch) {
    const [, pid, sid, filename] = mediaRelMatch;
    return `/api/projects/${pid}/scripts/${sid}/assets/media/${encodeURIComponent(filename)}`;
  }

  const exportRelMatch = u.match(
    /^projects\/([^/]+)\/scripts\/([^/]+)\/assets\/exports\/([^/]+)$/
  );
  if (exportRelMatch) {
    const [, pid, sid, filename] = exportRelMatch;
    return `/api/projects/${pid}/scripts/${sid}/assets/exports/${encodeURIComponent(filename)}`;
  }

  if (projectId && scriptId && !u.includes("/")) {
    if (/^final_.*\.mp4$/i.test(u)) {
      return `/api/projects/${projectId}/scripts/${scriptId}/assets/exports/${encodeURIComponent(u)}`;
    }
    return `/api/projects/${projectId}/scripts/${scriptId}/assets/media/${encodeURIComponent(u)}`;
  }

  if (u.startsWith("/")) return u;
  return "";
}

export function isPlayableMediaUrl(url: string | undefined): boolean {
  return Boolean(resolveMediaPlayUrl(url));
}
