/**
 * 资产详情弹窗壳层：遮罩 + 面板，统一 Modal 交互。
 */

import type { ReactNode } from "react";

interface AssetDetailShellProps {
  /** 面板标题 id，供 aria-labelledby 关联。 */
  titleId?: string;
  /** 额外 panel 类名（如 asset-detail-panel）。 */
  panelClassName?: string;
  /** 点击遮罩关闭。 */
  onClose: () => void;
  children: ReactNode;
}

/** 资产详情 Modal 外壳：固定遮罩、居中面板、阻止冒泡。 */
export function AssetDetailShell({
  titleId,
  panelClassName = "asset-detail-panel",
  onClose,
  children,
}: AssetDetailShellProps) {
  return (
    <div
      className="asset-editor-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      onClick={onClose}
    >
      <div
        className={`asset-editor-panel ${panelClassName}`.trim()}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
