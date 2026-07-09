/** OpenCut 参数注册表 label / option 翻译。 */

import i18n from "../../../i18n/config";

const PARAM_NS = "opencutParams";

/** 将参数 key 解析为当前语言标签。 */
export function translateParamLabel(paramKey: string, fallback?: string): string {
  return i18n.t(paramKey, {
    ns: PARAM_NS,
    defaultValue: fallback ?? paramKey,
  });
}

/** 将 select 选项 value 解析为当前语言标签。 */
export function translateParamOption(
  paramKey: string,
  optionValue: string,
  fallback?: string,
): string {
  const key = `options.${paramKey}.${optionValue}`;
  return i18n.t(key, {
    ns: PARAM_NS,
    defaultValue: fallback ?? optionValue,
  });
}

/** 关键帧切换按钮 tooltip。 */
export function translateKeyframeToggleTitle(paramLabel: string): string {
  return i18n.t("toggleKeyframe", {
    ns: PARAM_NS,
    label: paramLabel,
    defaultValue: `Toggle ${paramLabel} keyframe`,
  });
}
