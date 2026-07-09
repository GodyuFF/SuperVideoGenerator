/** 应用级 i18n Provider，确保 init 在首屏前完成。 */

import { I18nextProvider } from "react-i18next";
import { initI18n } from "./config";

const i18n = initI18n();

interface LocaleProviderProps {
  children: React.ReactNode;
}

/** 包裹应用根节点，注入 i18next 上下文。 */
export function LocaleProvider({ children }: LocaleProviderProps) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>;
}
