/**
 * 应用顶栏：统一品牌标识、状态区与导航操作区布局。
 */

import type { ReactNode } from "react";

export interface AppTopBarProps {
  /** 顶栏主标题，默认显示产品名。 */
  title?: ReactNode;
  /** 标题右侧徽章（如页面类型、AI 状态）。 */
  badge?: ReactNode;
  /** 顶栏左侧内容（返回按钮等）。 */
  lead?: ReactNode;
  /** 顶栏中部扩展区（项目切换器、状态徽章组）。 */
  center?: ReactNode;
  /** 顶栏右侧操作区（语言切换、配置入口）。 */
  trail?: ReactNode;
  /** 附加 class，用于设置页等变体。 */
  className?: string;
}

/** 渲染全站统一的胶片齿孔顶栏结构。 */
export function AppTopBar({
  title = "SuperVideoGenerator",
  badge,
  lead,
  center,
  trail,
  className = "",
}: AppTopBarProps) {
  return (
    <header className={`top-bar ${className}`.trim()}>
      {lead}
      <div className="svf-brand-mark">
        <span className="svf-brand-dot" aria-hidden />
        <h1>{title}</h1>
      </div>
      {badge}
      {center}
      <div className="top-bar-spacer" />
      {trail}
    </header>
  );
}
