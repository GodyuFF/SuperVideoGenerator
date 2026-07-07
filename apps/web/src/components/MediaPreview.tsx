/**
 * 媒体试听/预览：图片、视频、配音。
 */

import { isTimelinePlaceholderUrl, resolveMediaPlayUrl } from "../utils/mediaUrl";

interface MediaPreviewProps {
  kind: string;
  url?: string;
  label?: string;
  projectId?: string | null;
  scriptId?: string | null;
  className?: string;
}

export function MediaPreview({
  kind,
  url,
  label,
  projectId,
  scriptId,
  className = "media-preview",
}: MediaPreviewProps) {
  if (isTimelinePlaceholderUrl(url)) {
    return (
      <div className={`${className} media-preview-placeholder`}>
        {label ? <span className="media-preview-label muted">{label}</span> : null}
        <p className="muted">成片尚未导出。请在 Edit Studio 中确认时间轴素材齐全后，点击「导出成片」或使用 compose_final。</p>
      </div>
    );
  }

  const playUrl = resolveMediaPlayUrl(url, projectId, scriptId);
  if (!playUrl) return null;

  if (kind === "audio") {
    return (
      <div className={className}>
        {label ? <span className="media-preview-label muted">{label}</span> : null}
        <audio controls preload="metadata" src={playUrl} className="media-preview-audio" />
      </div>
    );
  }

  if (kind === "video" || kind === "final") {
    return (
      <div className={className}>
        <video controls preload="metadata" src={playUrl} className="media-preview-video" />
      </div>
    );
  }

  if (kind === "image") {
    return (
      <div className={className}>
        <img src={playUrl} alt={label ?? "preview"} className="media-preview-image" />
      </div>
    );
  }

  return null;
}
