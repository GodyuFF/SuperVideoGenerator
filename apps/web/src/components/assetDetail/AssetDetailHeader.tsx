/**
 * 资产详情页顶栏：类型徽章、标题与操作区；状态/报错独占第二行。
 */

import type { ReactNode } from "react";

interface AssetDetailHeaderProps {
  /** 类型或域标签（如「角色」「配音」）。 */
  typeLabel: string;
  /** 资产名称。 */
  title: string;
  /** 标题元素 id。 */
  titleId?: string;
  /** 右侧操作按钮组（不含长文案报错）。 */
  actions?: ReactNode;
  /** 顶栏下方全宽状态区（成功/失败提示等）。 */
  status?: ReactNode;
}

/** 详情 Modal / Drawer 共用顶栏布局。 */
export function AssetDetailHeader({
  typeLabel,
  title,
  titleId,
  actions,
  status,
}: AssetDetailHeaderProps) {
  return (
    <header
      className={`asset-editor-header asset-detail-header${status ? " asset-detail-header--has-status" : ""}`}
    >
      <div className="asset-detail-header__top">
        <div className="asset-detail-header__identity">
          <span className="asset-type-badge">{typeLabel}</span>
          <h3 id={titleId} className="asset-detail-header__title" title={title}>
            {title}
          </h3>
        </div>
        {actions ? <div className="asset-detail-actions">{actions}</div> : null}
      </div>
      {status ? <div className="asset-detail-header__status">{status}</div> : null}
    </header>
  );
}
