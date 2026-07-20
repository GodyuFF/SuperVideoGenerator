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

  const fileUriMatch = u.match(/^file:\/\/\/?(.+)$/i);
  if (fileUriMatch && projectId && scriptId) {
    const pathPart = decodeURIComponent(fileUriMatch[1].replace(/^\/([A-Za-z]:)/, "$1"));
    const filename = pathPart.split(/[/\\]/).pop();
    if (filename) {
      return `/api/projects/${projectId}/scripts/${scriptId}/assets/media/${encodeURIComponent(filename)}`;
    }
  }

  if (/^[A-Za-z]:\//.test(u) && projectId && scriptId) {
    const filename = u.split("/").pop();
    if (filename) {
      return `/api/projects/${projectId}/scripts/${scriptId}/assets/media/${encodeURIComponent(filename)}`;
    }
  }

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

/** 本地媒体/成片文件引用（可用于资源管理器 reveal）。 */
export interface MediaAssetFileRef {
  projectId: string;
  scriptId: string;
  filename: string;
  storage: "media" | "export";
}

/**
 * 从 MediaAsset.url 解析项目内落盘文件引用；远程 http(s) 或占位 URL 返回 null。
 */
export function parseMediaAssetFileRef(
  url: string | undefined,
  projectId?: string | null,
  scriptId?: string | null,
): MediaAssetFileRef | null {
  if (!url?.trim()) return null;
  const u = url.trim().replace(/\\/g, "/");
  if (isTimelinePlaceholderUrl(u)) return null;
  if (u.startsWith("http://") || u.startsWith("https://")) return null;

  const mediaRelMatch = u.match(
    /^projects\/([^/]+)\/scripts\/([^/]+)\/assets\/media\/([^/]+)$/,
  );
  if (mediaRelMatch) {
    const [, pid, sid, filename] = mediaRelMatch;
    return { projectId: pid, scriptId: sid, filename, storage: "media" };
  }

  const exportRelMatch = u.match(
    /^projects\/([^/]+)\/scripts\/([^/]+)\/assets\/exports\/([^/]+)$/,
  );
  if (exportRelMatch) {
    const [, pid, sid, filename] = exportRelMatch;
    return { projectId: pid, scriptId: sid, filename, storage: "export" };
  }

  const apiMediaMatch = u.match(
    /^\/api\/projects\/([^/]+)\/scripts\/([^/]+)\/assets\/media\/([^/?#]+)/,
  );
  if (apiMediaMatch) {
    const [, pid, sid, rawName] = apiMediaMatch;
    try {
      return {
        projectId: pid,
        scriptId: sid,
        filename: decodeURIComponent(rawName),
        storage: "media",
      };
    } catch {
      return { projectId: pid, scriptId: sid, filename: rawName, storage: "media" };
    }
  }

  const apiExportMatch = u.match(
    /^\/api\/projects\/([^/]+)\/scripts\/([^/]+)\/assets\/exports\/([^/?#]+)/,
  );
  if (apiExportMatch) {
    const [, pid, sid, rawName] = apiExportMatch;
    try {
      return {
        projectId: pid,
        scriptId: sid,
        filename: decodeURIComponent(rawName),
        storage: "export",
      };
    } catch {
      return { projectId: pid, scriptId: sid, filename: rawName, storage: "export" };
    }
  }

  if (projectId && scriptId && !u.includes("/")) {
    if (/^final_.*\.mp4$/i.test(u)) {
      return { projectId, scriptId, filename: u, storage: "export" };
    }
    return { projectId, scriptId, filename: u, storage: "media" };
  }

  return null;
}

export function isPlayableMediaUrl(url: string | undefined): boolean {
  return Boolean(resolveMediaPlayUrl(url));
}
