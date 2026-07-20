/**
 * 资产详情内容区块：统一 section 标题与可选附加类名。
 */

import type { ReactNode } from "react";

interface AssetDetailSectionProps {
  /** 区块标题；省略则不渲染标题行。 */
  title?: string;
  /** 附加 section 类名。 */
  className?: string;
  children: ReactNode;
}

/** 详情页内容分区，采用取景器卡片样式。 */
export function AssetDetailSection({
  title,
  className = "",
  children,
}: AssetDetailSectionProps) {
  const sectionClass = ["asset-detail-section", className].filter(Boolean).join(" ");
  return (
    <section className={sectionClass}>
      {title ? <h4 className="asset-detail-section__title">{title}</h4> : null}
      {children}
    </section>
  );
}
