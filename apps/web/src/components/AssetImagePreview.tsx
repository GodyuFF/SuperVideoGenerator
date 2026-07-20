/**
 * 图文资产图片预览：固定尺寸容器内 object-fit contain；详情态可点击大图。
 * 加载失败或非可用 URL 时展示暗房占位，避免浏览器破图图标。
 */

import { useEffect, useRef, useState } from "react";
import { resolveMediaPlayUrl } from "../utils/mediaUrl";
import {
  looksLikeMediaUrl,
  looksLikeVideoUrl,
} from "../utils/boardMediaPreview";
import { AssetImageLightbox } from "./assetDetail/AssetImageLightbox";

interface AssetImagePreviewProps {
  url: string;
  alt?: string;
  name?: string;
  size?: "card" | "detail";
  /** character/prop 透明 PNG 用棋盘格底展示 */
  checkerboard?: boolean;
  projectId?: string | null;
  scriptId?: string | null;
  /** 允许点击放大（默认 detail 尺寸开启）。 */
  enableLightbox?: boolean;
  /** 媒体不可用（空 URL / 非法 / 加载失败）时回调，便于父级折叠预览区。 */
  onUnavailable?: () => void;
  /** 无可用媒体时隐藏整块（默认展示占位）。 */
  hideWhenUnavailable?: boolean;
  /** 占位文案（无图/加载失败）。 */
  unavailableLabel?: string;
}

/** 图文资产缩略图 / 详情图预览。 */
export function AssetImagePreview({
  url,
  alt = "",
  name,
  size = "card",
  checkerboard = false,
  projectId,
  scriptId,
  enableLightbox,
  onUnavailable,
  hideWhenUnavailable = false,
  unavailableLabel = "",
}: AssetImagePreviewProps) {
  const playUrl = resolveMediaPlayUrl(url, projectId, scriptId) || url;
  const canAttempt = Boolean(playUrl && looksLikeMediaUrl(playUrl));
  const asVideo = canAttempt && looksLikeVideoUrl(playUrl);
  const [failed, setFailed] = useState(false);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const notifiedRef = useRef(false);

  useEffect(() => {
    setFailed(false);
    notifiedRef.current = false;
  }, [playUrl]);

  const unavailable = !canAttempt || failed;
  const canLightbox = (enableLightbox ?? size === "detail") && !unavailable && !asVideo;

  useEffect(() => {
    if (!unavailable || notifiedRef.current) return;
    notifiedRef.current = true;
    onUnavailable?.();
  }, [unavailable, onUnavailable]);

  const frameClass =
    size === "detail" ? "asset-image-frame asset-image-frame--detail" : "asset-image-frame";
  const frameWithBg = checkerboard
    ? `${frameClass} asset-image-frame--checkerboard`
    : frameClass;

  /** 打开大图预览。 */
  const openLightbox = () => {
    if (!canLightbox || !playUrl) return;
    setLightboxOpen(true);
  };

  /** 标记媒体加载失败。 */
  const markFailed = () => {
    setFailed(true);
  };

  if (unavailable && hideWhenUnavailable) {
    return null;
  }

  const label = unavailableLabel || name?.slice(0, 1) || "·";

  return (
    <>
      <figure
        className={`asset-image-preview${unavailable ? " asset-image-preview--unavailable" : ""}`}
      >
        <div className={frameWithBg}>
          {unavailable ? (
            <div className="asset-image-frame__fallback" aria-hidden>
              <span className="asset-image-frame__fallback-mark">{label}</span>
            </div>
          ) : asVideo ? (
            <video
              className="asset-image-frame__video"
              src={playUrl}
              muted
              playsInline
              preload="metadata"
              onError={markFailed}
              aria-label={alt || name || "video preview"}
            />
          ) : canLightbox ? (
            <button
              type="button"
              className="asset-image-preview__hit"
              onClick={openLightbox}
              aria-label={name || alt || "preview"}
            >
              <img src={playUrl} alt={alt || name || ""} loading="lazy" onError={markFailed} />
            </button>
          ) : (
            <img src={playUrl} alt={alt || name || ""} loading="lazy" onError={markFailed} />
          )}
        </div>
        {name ? <figcaption>{name}</figcaption> : null}
      </figure>
      {lightboxOpen ? (
        <AssetImageLightbox
          src={playUrl}
          alt={alt || name || ""}
          onClose={() => setLightboxOpen(false)}
        />
      ) : null}
    </>
  );
}
