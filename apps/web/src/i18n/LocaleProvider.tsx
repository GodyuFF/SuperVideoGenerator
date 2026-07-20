/** 应用级 i18n Provider：初始化后从后端 hydrate 界面语言。 */

import { useEffect } from "react";
import { I18nextProvider, useTranslation } from "react-i18next";
import { initI18n } from "./config";
import {
  applyDocumentLang,
  applyAppLocale,
  coerceAppLocale,
  fetchUiLocaleFromApi,
} from "./localeSync";

const i18n = initI18n();
applyDocumentLang(i18n.language === "en" ? "en" : "zh-CN");

interface LocaleProviderProps {
  children: React.ReactNode;
}

/** 启动时拉取 /api/ui-prefs 并对齐 i18n。 */
function LocaleHydrator({ children }: { children: React.ReactNode }) {
  const { i18n: i18nInst } = useTranslation();

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const remote = await fetchUiLocaleFromApi();
      if (cancelled || !remote) return;
      const current = i18nInst.language === "en" ? "en" : "zh-CN";
      if (remote !== current) {
        await i18nInst.changeLanguage(remote);
      }
      applyDocumentLang(remote);
      // 已与后端一致，不必再 PATCH；也不在 hydrate 时覆写 TTS
      await applyAppLocale(remote, { persistRemote: false, syncTts: false });
    })();
    return () => {
      cancelled = true;
    };
  }, [i18nInst]);

  useEffect(() => {
    /** 语言变更时同步 document.lang（含非 LocaleSwitcher 路径）。 */
    const onChanged = (lng: string) => {
      const locale = coerceAppLocale(lng);
      if (locale) applyDocumentLang(locale);
    };
    i18nInst.on("languageChanged", onChanged);
    return () => {
      i18nInst.off("languageChanged", onChanged);
    };
  }, [i18nInst]);

  return <>{children}</>;
}

/** 包裹应用根节点，注入 i18next 上下文。 */
export function LocaleProvider({ children }: LocaleProviderProps) {
  return (
    <I18nextProvider i18n={i18n}>
      <LocaleHydrator>{children}</LocaleHydrator>
    </I18nextProvider>
  );
}
