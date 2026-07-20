/**
 * 服务端导出文件：另存为 / 下载，并在本机资源管理器中定位项目导出目录。
 */

import { parseMediaAssetFileRef } from "./mediaUrl";

const API = "/api";

export type SaveExportMethod = "save-picker" | "anchor-download";

export interface SaveExportResult {
  saved: boolean;
  method: SaveExportMethod;
  filename: string;
}

export interface SaveExportAndRevealResult extends SaveExportResult {
  revealed: boolean;
  revealError?: string;
}

/** 从导出 API URL 解析文件名。 */
export function parseExportFilename(exportUrl: string): string {
  const clean = exportUrl.split("?")[0] ?? exportUrl;
  const parts = clean.split("/");
  const last = parts[parts.length - 1] ?? "";
  try {
    return decodeURIComponent(last);
  } catch {
    return last;
  }
}

/** 将相对 API 路径转为可 fetch 的绝对 URL。 */
export function toAbsoluteApiUrl(pathOrUrl: string): string {
  if (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")) {
    return pathOrUrl;
  }
  if (pathOrUrl.startsWith("/")) {
    return `${window.location.origin}${pathOrUrl}`;
  }
  return `${window.location.origin}${API}/${pathOrUrl.replace(/^\//, "")}`;
}

function acceptTypesForFilename(filename: string): FilePickerAcceptType[] {
  if (filename.toLowerCase().endsWith(".zip")) {
    return [{ accept: { "application/zip": [".zip"] } }];
  }
  return [{ accept: { "video/mp4": [".mp4"] } }];
}

function triggerAnchorDownload(blob: Blob, filename: string): void {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(objectUrl);
}

/**
 * 拉取导出文件并保存：优先系统「另存为」对话框，否则触发浏览器下载。
 */
export async function saveExportFromApiUrl(
  exportUrl: string,
  suggestedFilename: string,
): Promise<SaveExportResult> {
  const absoluteUrl = toAbsoluteApiUrl(exportUrl);
  const response = await fetch(absoluteUrl);
  if (!response.ok) {
    throw new Error(`下载导出文件失败（${response.status}）`);
  }
  const blob = await response.blob();
  const filename = suggestedFilename || parseExportFilename(exportUrl) || "export.bin";

  const picker = window.showSaveFilePicker;
  if (typeof picker === "function") {
    try {
      const handle = await picker({
        suggestedName: filename,
        types: acceptTypesForFilename(filename),
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return { saved: true, method: "save-picker", filename };
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        throw new Error("已取消保存");
      }
    }
  }

  triggerAnchorDownload(blob, filename);
  return { saved: true, method: "anchor-download", filename };
}

/**
 * 请求后端在系统文件管理器中定位项目 exports 目录下的文件。
 */
export async function revealExportInFolder(
  projectId: string,
  scriptId: string,
  filename: string,
): Promise<void> {
  const safeName = encodeURIComponent(filename);
  const res = await fetch(
    `${API}/projects/${projectId}/scripts/${scriptId}/assets/exports/${safeName}/reveal`,
    { method: "POST" },
  );
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail || `无法打开所在文件夹（${res.status}）`);
  }
}

/**
 * 请求后端在系统文件管理器中定位项目 media 目录下的文件。
 */
export async function revealMediaInFolder(
  projectId: string,
  scriptId: string,
  filename: string,
): Promise<void> {
  const safeName = encodeURIComponent(filename);
  const res = await fetch(
    `${API}/projects/${projectId}/scripts/${scriptId}/assets/media/${safeName}/reveal`,
    { method: "POST" },
  );
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail || `无法打开所在文件夹（${res.status}）`);
  }
}

/**
 * 根据 MediaAsset.url 解析引用并在资源管理器中定位文件。
 */
export async function revealMediaAssetFromUrl(
  url: string | undefined,
  projectId?: string | null,
  scriptId?: string | null,
): Promise<void> {
  const ref = parseMediaAssetFileRef(url, projectId, scriptId);
  if (!ref) {
    throw new Error("该媒体无本地文件路径，无法在文件夹中打开");
  }
  if (ref.storage === "export") {
    await revealExportInFolder(ref.projectId, ref.scriptId, ref.filename);
    return;
  }
  await revealMediaInFolder(ref.projectId, ref.scriptId, ref.filename);
}

/** 保存导出文件并在资源管理器中定位（服务端 exports 目录）。 */
export async function saveExportAndReveal(
  projectId: string,
  scriptId: string,
  exportUrl: string,
  suggestedFilename?: string,
): Promise<SaveExportAndRevealResult> {
  const filename =
    suggestedFilename ||
    parseExportFilename(exportUrl) ||
    `export_${scriptId}_${Date.now()}.mp4`;
  const result = await saveExportFromApiUrl(exportUrl, filename);
  const revealName = parseExportFilename(exportUrl) || filename;
  try {
    await revealExportInFolder(projectId, scriptId, revealName);
    return { ...result, revealed: true };
  } catch (err) {
    return {
      ...result,
      revealed: false,
      revealError: err instanceof Error ? err.message : String(err),
    };
  }
}
