/**
 * 应用页面外壳：包裹顶栏与主内容区的标准页面骨架。
 */

import type { ReactNode } from "react";
import { AppTopBar, type AppTopBarProps } from "./AppTopBar";

export interface AppShellProps extends AppTopBarProps {
  /** 主内容区。 */
  children: ReactNode;
  /** 根容器 class（如 project-home、settings-page）。 */
  pageClass?: string;
  /** 主内容区 class。 */
  mainClass?: string;
  /** 顶栏与主内容之间的横幅（如 AI 未配置提示）。 */
  banner?: ReactNode;
}

/** 组合顶栏、可选横幅与主内容，供各独立页面复用。 */
export function AppShell({
  children,
  pageClass = "",
  mainClass = "",
  banner,
  ...topBarProps
}: AppShellProps) {
  return (
    <div className={pageClass}>
      <AppTopBar {...topBarProps} />
      {banner}
      <main className={mainClass}>{children}</main>
    </div>
  );
}
