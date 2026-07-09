/** 在 documentElement 挂载 SVF 主题作用域，供 Portal 下拉层继承令牌。 */

import { useEffect } from "react";

const HTML_THEME_CLASS = "svf-opencut-active";

/** OpenCut 嵌入期间为 html 添加主题类，卸载时移除。 */
export function useSvfOpencutThemeScope(enabled = true): void {
  useEffect(() => {
    if (!enabled) return;
    document.documentElement.classList.add(HTML_THEME_CLASS);
    return () => {
      document.documentElement.classList.remove(HTML_THEME_CLASS);
    };
  }, [enabled]);
}
