/** 关系图资产 kind 列表（图例顺序）。 */
export const LEGEND_KINDS = [
  "project",
  "script",
  "character",
  "scene",
  "prop",
  "plot",
  "frame",
  "video_clip",
  "video_plan",
  "image",
  "video",
  "audio",
  "final",
] as const;

/** 返回 kind 对应的设计系统 CSS 变量名。 */
export function graphKindCssVar(kind: string): string {
  return `--svf-graph-kind-${kind}`;
}

/** 从 document 根节点读取关系图 kind 颜色（随 light/dark 切换）。 */
export function readGraphKindColor(kind: string, root: HTMLElement = document.documentElement): string {
  const style = getComputedStyle(root);
  const named = style.getPropertyValue(graphKindCssVar(kind)).trim();
  if (named) return named;
  return style.getPropertyValue("--svf-graph-kind-fallback").trim() || "#64748b";
}

/** 读取单个关系图主题令牌。 */
export function readGraphThemeToken(token: string, root: HTMLElement = document.documentElement): string {
  return getComputedStyle(root).getPropertyValue(token).trim();
}
