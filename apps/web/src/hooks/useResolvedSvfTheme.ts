/**
 * 解析当前生效的 SVF 主题（light / dark）。
 */

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";

/** 返回已解析的明暗主题，hydration 前默认 dark。 */
export function useResolvedSvfTheme(): "light" | "dark" {
  const { resolvedTheme } = useTheme();
  const [theme, setTheme] = useState<"light" | "dark">("dark");

  useEffect(() => {
    setTheme(resolvedTheme === "light" ? "light" : "dark");
  }, [resolvedTheme]);

  return theme;
}
