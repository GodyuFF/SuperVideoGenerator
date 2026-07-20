/** 全局中/英语言切换控件（同步后端 prefs + TTS 默认语言）。 */

import { useTranslation } from "react-i18next";
import type { AppLocale } from "./config";
import { applyAppLocale } from "./localeSync";

interface LocaleSwitcherProps {
  className?: string;
}

/** 顶栏语言切换：中文 | EN。 */
export function LocaleSwitcher({ className = "locale-switcher" }: LocaleSwitcherProps) {
  const { i18n, t } = useTranslation("nav");

  const current = (i18n.language === "en" ? "en" : "zh-CN") as AppLocale;

  /** 切换到指定语言并写入本机单源配置。 */
  const setLocale = (locale: AppLocale) => {
    if (locale === current) return;
    void (async () => {
      await i18n.changeLanguage(locale);
      await applyAppLocale(locale, { persistRemote: true, syncTts: true });
    })();
  };

  return (
    <div className={className} role="group" aria-label={t("language")}>
      <button
        type="button"
        className={`btn-secondary btn-sm locale-switcher-btn${current === "zh-CN" ? " is-active" : ""}`}
        onClick={() => setLocale("zh-CN")}
      >
        中文
      </button>
      <button
        type="button"
        className={`btn-secondary btn-sm locale-switcher-btn${current === "en" ? " is-active" : ""}`}
        onClick={() => setLocale("en")}
      >
        EN
      </button>
    </div>
  );
}
