/**
 * 浏览器端 audio/video File 真实时长探测（与 OpenCut processing 逻辑一致）。
 */

/** 从 File 探测媒体时长（秒）；失败时 reject。 */
export function probeMediaDuration(file: File): Promise<number> {
  return new Promise((resolve, reject) => {
    const isVideo = file.type.startsWith("video/");
    const element = document.createElement(
      isVideo ? "video" : "audio",
    ) as HTMLVideoElement;
    const objectUrl = URL.createObjectURL(file);

    element.addEventListener("loadedmetadata", () => {
      const seconds = element.duration;
      URL.revokeObjectURL(objectUrl);
      element.remove();
      if (!Number.isFinite(seconds) || seconds <= 0) {
        reject(new Error("Invalid media duration"));
        return;
      }
      resolve(seconds);
    });

    element.addEventListener("error", () => {
      URL.revokeObjectURL(objectUrl);
      element.remove();
      reject(new Error("Could not load media"));
    });

    element.src = objectUrl;
    element.load();
  });
}

/** 解析媒体时长秒数：优先已有值，否则从 File 探测。 */
export async function resolveMediaDurationSeconds(asset: {
  duration?: number | null;
  file?: File;
  type: string;
}): Promise<number | undefined> {
  if (asset.duration != null && asset.duration > 0 && Number.isFinite(asset.duration)) {
    return asset.duration;
  }
  if (
    !asset.file ||
    asset.file.size === 0 ||
    (asset.type !== "audio" && asset.type !== "video")
  ) {
    return asset.duration ?? undefined;
  }
  try {
    return await probeMediaDuration(asset.file);
  } catch {
    return asset.duration ?? undefined;
  }
}
