/** Next.js Image 兼容层。 */
import type { ImgHTMLAttributes } from "react";

type ImageProps = ImgHTMLAttributes<HTMLImageElement> & {
  src: string;
  alt: string;
  width?: number;
  height?: number;
  fill?: boolean;
  priority?: boolean;
  unoptimized?: boolean;
};

/** 替代 next/image。 */
export default function Image({
  src,
  alt,
  width,
  height,
  style,
  fill,
  priority: _priority,
  unoptimized: _unoptimized,
  ...rest
}: ImageProps) {
  const mergedStyle = fill
    ? { ...style, width: "100%", height: "100%", objectFit: "cover" as const }
    : style;
  return <img src={src} alt={alt} width={width} height={height} style={mergedStyle} {...rest} />;
}
