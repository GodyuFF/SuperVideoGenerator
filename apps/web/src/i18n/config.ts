/**
 * i18next 初始化与语言持久化。
 */

import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import zhCommon from "./locales/zh-CN/common.json";
import zhNav from "./locales/zh-CN/nav.json";
import zhBoard from "./locales/zh-CN/board.json";
import zhChat from "./locales/zh-CN/chat.json";
import zhSettings from "./locales/zh-CN/settings.json";
import zhEditor from "./locales/zh-CN/editor.json";
import zhOpencutTimeline from "./locales/zh-CN/opencut/timeline.json";
import zhOpencutAssets from "./locales/zh-CN/opencut/assets.json";
import zhOpencutExport from "./locales/zh-CN/opencut/export.json";
import zhOpencutProperties from "./locales/zh-CN/opencut/properties.json";
import zhOpencutShortcuts from "./locales/zh-CN/opencut/shortcuts.json";
import zhOpencutDialogs from "./locales/zh-CN/opencut/dialogs.json";
import zhOpencutLanding from "./locales/zh-CN/opencut/landing.json";
import zhOpencutCommon from "./locales/zh-CN/opencut/common.json";
import zhOpencutParams from "./locales/zh-CN/opencut/params.json";
import zhPlan from "./locales/zh-CN/plan.json";

import enCommon from "./locales/en/common.json";
import enNav from "./locales/en/nav.json";
import enBoard from "./locales/en/board.json";
import enChat from "./locales/en/chat.json";
import enSettings from "./locales/en/settings.json";
import enEditor from "./locales/en/editor.json";
import enOpencutTimeline from "./locales/en/opencut/timeline.json";
import enOpencutAssets from "./locales/en/opencut/assets.json";
import enOpencutExport from "./locales/en/opencut/export.json";
import enOpencutProperties from "./locales/en/opencut/properties.json";
import enOpencutShortcuts from "./locales/en/opencut/shortcuts.json";
import enOpencutDialogs from "./locales/en/opencut/dialogs.json";
import enOpencutLanding from "./locales/en/opencut/landing.json";
import enOpencutCommon from "./locales/en/opencut/common.json";
import enOpencutParams from "./locales/en/opencut/params.json";
import enPlan from "./locales/en/plan.json";

export const LOCALE_STORAGE_KEY = "svg.locale";
export const SUPPORTED_LOCALES = ["zh-CN", "en"] as const;
export type AppLocale = (typeof SUPPORTED_LOCALES)[number];

/** 从 localStorage 读取已保存语言。 */
export function readStoredLocale(): AppLocale {
  const raw = localStorage.getItem(LOCALE_STORAGE_KEY);
  if (raw === "en" || raw === "zh-CN") return raw;
  return "zh-CN";
}

/** 持久化语言选择。 */
export function persistLocale(locale: AppLocale): void {
  localStorage.setItem(LOCALE_STORAGE_KEY, locale);
}

const resources = {
  "zh-CN": {
    common: zhCommon,
    nav: zhNav,
    board: zhBoard,
    chat: zhChat,
    settings: zhSettings,
    editor: zhEditor,
    opencutTimeline: zhOpencutTimeline,
    opencutAssets: zhOpencutAssets,
    opencutExport: zhOpencutExport,
    opencutProperties: zhOpencutProperties,
    opencutShortcuts: zhOpencutShortcuts,
    opencutDialogs: zhOpencutDialogs,
    opencutLanding: zhOpencutLanding,
    opencutCommon: zhOpencutCommon,
    opencutParams: zhOpencutParams,
    plan: zhPlan,
  },
  en: {
    common: enCommon,
    nav: enNav,
    board: enBoard,
    chat: enChat,
    settings: enSettings,
    editor: enEditor,
    opencutTimeline: enOpencutTimeline,
    opencutAssets: enOpencutAssets,
    opencutExport: enOpencutExport,
    opencutProperties: enOpencutProperties,
    opencutShortcuts: enOpencutShortcuts,
    opencutDialogs: enOpencutDialogs,
    opencutLanding: enOpencutLanding,
    opencutCommon: enOpencutCommon,
    opencutParams: enOpencutParams,
    plan: enPlan,
  },
};

let initialized = false;

/** 初始化 i18next（幂等）。 */
export function initI18n(): typeof i18n {
  if (initialized) return i18n;
  initialized = true;

  void i18n.use(initReactI18next).init({
    resources,
    lng: readStoredLocale(),
    fallbackLng: "zh-CN",
    supportedLngs: [...SUPPORTED_LOCALES],
    defaultNS: "common",
    ns: [
      "common",
      "nav",
      "board",
      "chat",
      "settings",
      "editor",
      "opencutTimeline",
      "opencutAssets",
      "opencutExport",
      "opencutProperties",
      "opencutShortcuts",
      "opencutDialogs",
      "opencutLanding",
      "opencutCommon",
      "opencutParams",
      "plan",
    ],
    interpolation: { escapeValue: false },
    returnEmptyString: false,
  });

  i18n.on("languageChanged", (lng) => {
    if (lng === "zh-CN" || lng === "en") persistLocale(lng);
  });

  return i18n;
}

export default i18n;
