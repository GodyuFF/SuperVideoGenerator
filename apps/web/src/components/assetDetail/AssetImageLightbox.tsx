/**
 * 资产详情图片大图预览层：点击缩略图放大，Esc / 遮罩关闭。
 */

import { useEffect } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";

interface AssetImageLightboxProps {
  /** 可播放的图片 URL。 */
  src: string;
  /** 替代文案 / 标题。 */
  alt?: string;
  /** 关闭回调。 */
  onClose: () => void;
}

/** 全屏暗房风大图预览。 */
export function AssetImageLightbox({
  src,
  alt = "",
  onClose,
}: AssetImageLightboxProps) {
  const { t } = useAppTranslation("common");

  useEffect(() => {
    /** Esc 关闭大图。 */
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  return (
    <div
      className="asset-image-lightbox"
      role="dialog"
      aria-modal="true"
      aria-label={t("actions.previewImage")}
      onClick={onClose}
    >
      <button
        type="button"
        className="btn-secondary btn-sm asset-image-lightbox__close"
        onClick={onClose}
      >
        {t("actions.close")}
      </button>
      <img
        className="asset-image-lightbox__img"
        src={src}
        alt={alt}
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  );
}
