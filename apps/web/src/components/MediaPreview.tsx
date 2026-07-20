/**
 * 媒体预览：图片、视频、配音；支持列表缩略图固定尺寸模式。
 */

import { isTimelinePlaceholderUrl, resolveMediaPlayUrl } from "../utils/mediaUrl";

interface MediaPreviewProps {
  kind: string;
  url?: string;
  label?: string;
  projectId?: string | null;
  scriptId?: string | null;
  className?: string;
  /** 看板媒体页等场景：固定比例缩略图，不展示完整控件。 */
  variant?: "default" | "thumb";
}

/** 渲染可播放/可预览的媒体元素。 */
export function MediaPreview({
  kind,
  url,
  label,
  projectId,
  scriptId,
  className = "media-preview",
  variant = "default",
}: MediaPreviewProps) {
  const isThumb = variant === "thumb";
  const rootClass = isThumb ? `${className} media-preview--thumb` : className;

  if (isTimelinePlaceholderUrl(url)) {
    return (
      <div className={`${rootClass} media-preview-placeholder`}>
        {label ? <span className="media-preview-label muted">{label}</span> : null}
        <p className="muted">
          {isThumb
            ? "未导出"
            : "成片尚未导出。请在 Edit Studio 中确认时间轴素材齐全后，点击「导出成片」或使用 compose_final。"}
        </p>
      </div>
    );
  }

  const playUrl = resolveMediaPlayUrl(url, projectId, scriptId);
  if (!playUrl) return null;

  if (kind === "audio") {
    return (
      <div className={rootClass}>
        {label && !isThumb ? (
          <span className="media-preview-label muted">{label}</span>
        ) : null}
        <audio
          controls={!isThumb}
          preload="metadata"
          src={playUrl}
          className="media-preview-audio"
        />
      </div>
    );
  }

  if (kind === "video" || kind === "final") {
    return (
      <div className={rootClass}>
        <video
          controls={!isThumb}
          preload="metadata"
          muted={isThumb}
          playsInline
          src={playUrl}
          className="media-preview-video"
        />
      </div>
    );
  }

  if (kind === "image") {
    return (
      <div className={rootClass}>
        <img src={playUrl} alt={label ?? "preview"} className="media-preview-image" />
      </div>
    );
  }

  return null;
}
