/**
 * 订阅 SVF 明暗主题，读取关系图 CSS 变量供 React Flow 等 JS API 使用。
 */

import { useMemo } from "react";
import { useResolvedSvfTheme } from "../../../hooks/useResolvedSvfTheme";
import { readGraphKindColor, readGraphThemeToken } from "./kindColors";

/** 关系图运行时主题色（MiniMap、Background 等需 JS 字符串的场景）。 */
export function useGraphThemeColors() {
  const theme = useResolvedSvfTheme();

  return useMemo(
    () => ({
      dotColor: readGraphThemeToken("--svf-graph-dot") || "rgba(128,128,128,0.12)",
      minimapMaskColor: readGraphThemeToken("--svf-graph-minimap-mask") || "rgba(224, 99, 74, 0.12)",
      getKindColor: (kind: string) => readGraphKindColor(kind),
    }),
    [theme],
  );
}
