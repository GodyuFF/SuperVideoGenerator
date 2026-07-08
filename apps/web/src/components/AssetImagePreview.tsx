/**
 * 图文资产图片预览：固定尺寸容器内 object-fit contain，避免原图撑破布局。
 */

export function AssetImagePreview({
  url,
  alt = "",
  name,
  size = "card",
  checkerboard = false,
}: {
  url: string;
  alt?: string;
  name?: string;
  size?: "card" | "detail";
  /** character/prop 透明 PNG 用棋盘格底展示 */
  checkerboard?: boolean;
}) {
  const frameClass =
    size === "detail" ? "asset-image-frame asset-image-frame--detail" : "asset-image-frame";
  const frameWithBg = checkerboard
    ? `${frameClass} asset-image-frame--checkerboard`
    : frameClass;
  return (
    <figure className="asset-image-preview">
      <div className={frameWithBg}>
        <img src={url} alt={alt || name || ""} loading="lazy" />
      </div>
      {name ? <figcaption>{name}</figcaption> : null}
    </figure>
  );
}
