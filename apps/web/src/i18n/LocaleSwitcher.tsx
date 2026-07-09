/** 全局中/英语言切换控件。 */

import { useTranslation } from "react-i18next";
import type { AppLocale } from "./config";

interface LocaleSwitcherProps {
  className?: string;
}

/** 顶栏语言切换：中文 | EN。 */
export function LocaleSwitcher({ className = "locale-switcher" }: LocaleSwitcherProps) {
  const { i18n, t } = useTranslation("nav");

  const current = (i18n.language === "en" ? "en" : "zh-CN") as AppLocale;

  /** 切换到指定语言。 */
  const setLocale = (locale: AppLocale) => {
    if (locale !== current) void i18n.changeLanguage(locale);
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
