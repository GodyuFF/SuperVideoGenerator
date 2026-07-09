/**
 * OpenCut 注册表 labelKey → 翻译文案。
 */

import i18n from "./config";

/** 将注册表 labelKey 解析为当前语言文案（格式 namespace.rest.of.key）。 */
export function translateRegistryLabel(labelKey: string): string {
  const dot = labelKey.indexOf(".");
  if (dot <= 0) return labelKey;
  const ns = labelKey.slice(0, dot);
  const key = labelKey.slice(dot + 1);
  return i18n.t(key, { ns, defaultValue: labelKey });
}
