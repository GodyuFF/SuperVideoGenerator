/**
 * 全局主题提供者：统一主应用与 OpenCut 嵌入区的明暗模式。
 */

import type { ReactNode } from "react";
import { ThemeProvider } from "next-themes";

const STORAGE_KEY = "svf-theme";

interface SvfThemeProviderProps {
  children: ReactNode;
}

/** 挂载 next-themes，通过 html class 切换 light/dark。 */
export function SvfThemeProvider({ children }: SvfThemeProviderProps) {
  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="dark"
      enableSystem
      storageKey={STORAGE_KEY}
      disableTransitionOnChange={false}
    >
      {children}
    </ThemeProvider>
  );
}
