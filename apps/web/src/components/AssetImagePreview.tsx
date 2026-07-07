/**
 * 图文资产图片预览：固定尺寸容器内 object-fit contain，避免原图撑破布局。
 */

export function AssetImagePreview({
  url,
  alt = "",
  name,
  size = "card",
}: {
  url: string;
  alt?: string;
  name?: string;
  size?: "card" | "detail";
}) {
  const frameClass =
    size === "detail" ? "asset-image-frame asset-image-frame--detail" : "asset-image-frame";
  return (
    <figure className="asset-image-preview">
      <div className={frameClass}>
        <img src={url} alt={alt || name || ""} loading="lazy" />
      </div>
      {name ? <figcaption>{name}</figcaption> : null}
    </figure>
  );
}
