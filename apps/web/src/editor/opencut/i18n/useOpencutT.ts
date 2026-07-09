/** OpenCut 嵌入层翻译 Hook 封装。 */

import { useTranslation } from "react-i18next";

/** 获取 OpenCut 相关命名空间的 t 函数。 */
export function useOpencutT() {
  const timeline = useTranslation("opencutTimeline");
  const assets = useTranslation("opencutAssets");
  const exportNs = useTranslation("opencutExport");
  const properties = useTranslation("opencutProperties");
  const shortcuts = useTranslation("opencutShortcuts");
  const dialogs = useTranslation("opencutDialogs");
  const landing = useTranslation("opencutLanding");
  const common = useTranslation("opencutCommon");
  const params = useTranslation("opencutParams");

  return {
    tTimeline: timeline.t,
    tAssets: assets.t,
    tExport: exportNs.t,
    tProperties: properties.t,
    tShortcuts: shortcuts.t,
    tDialogs: dialogs.t,
    tLanding: landing.t,
    tCommon: common.t,
    tParams: params.t,
    i18n: timeline.i18n,
  };
}

/** 解析快捷键 action 描述。 */
export function translateActionDescription(actionId: string): string {
  const { t } = useTranslation("opencutShortcuts");
  return t(`actions.${actionId}`, { defaultValue: actionId });
}

/** 解析快捷键分类名。 */
export function translateActionCategory(category: string): string {
  const { t } = useTranslation("opencutShortcuts");
  return t(`categories.${category}`, { defaultValue: category });
}
