/**
 * 按命名空间封装的翻译 Hook。
 */

import { useTranslation, type UseTranslationOptions } from "react-i18next";

export type AppNamespace =
  | "common"
  | "nav"
  | "plan"
  | "board"
  | "chat"
  | "settings"
  | "editor"
  | "opencutTimeline"
  | "opencutAssets"
  | "opencutExport"
  | "opencutProperties"
  | "opencutShortcuts"
  | "opencutDialogs"
  | "opencutLanding"
  | "opencutCommon";

/** 获取指定命名空间的 t 函数与 i18n 实例。 */
export function useAppTranslation(
  ns: AppNamespace | AppNamespace[],
  options?: UseTranslationOptions<AppNamespace>,
) {
  return useTranslation(ns, options);
}
