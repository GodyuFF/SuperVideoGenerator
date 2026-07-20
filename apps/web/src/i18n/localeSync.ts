/**
 * UI 语言与后端 / TTS 同步工具。
 */

import type { AppLocale } from "./config";
import { persistLocale, SUPPORTED_LOCALES } from "./config";

const UI_PREFS_API = "/api/ui-prefs";
const AI_CONFIG_API = "/api/ai/config";

/** 将任意字符串规范为 AppLocale；无法识别时返回 null。 */
export function coerceAppLocale(raw: string | null | undefined): AppLocale | null {
  const value = String(raw || "").trim();
  if ((SUPPORTED_LOCALES as readonly string[]).includes(value)) {
    return value as AppLocale;
  }
  return null;
}

/** 同步 document.documentElement.lang。 */
export function applyDocumentLang(locale: AppLocale): void {
  if (typeof document !== "undefined") {
    document.documentElement.lang = locale;
  }
}

/** 从后端拉取 ui_locale；失败返回 null。 */
export async function fetchUiLocaleFromApi(): Promise<AppLocale | null> {
  try {
    const res = await fetch(UI_PREFS_API);
    if (!res.ok) return null;
    const data = (await res.json()) as { ui_locale?: string };
    return coerceAppLocale(data.ui_locale);
  } catch {
    return null;
  }
}

/** 将 ui_locale 写入后端；失败静默（不阻断 UI）。 */
export async function persistUiLocaleToApi(locale: AppLocale): Promise<void> {
  try {
    await fetch(UI_PREFS_API, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ui_locale: locale }),
    });
  } catch {
    /* 离线时仅依赖 localStorage */
  }
}

/** 将 TTS 默认语言同步为界面语言。 */
export async function syncTtsDefaultLanguage(locale: AppLocale): Promise<void> {
  try {
    await fetch(AI_CONFIG_API, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tts: { default_language: locale } }),
    });
  } catch {
    /* TTS 同步失败不阻断语言切换 */
  }
}

/**
 * 应用语言：localStorage + document.lang + 可选后端 / TTS。
 */
export async function applyAppLocale(
  locale: AppLocale,
  options: {
    persistRemote?: boolean;
    syncTts?: boolean;
  } = {},
): Promise<void> {
  const { persistRemote = true, syncTts = true } = options;
  persistLocale(locale);
  applyDocumentLang(locale);
  const tasks: Promise<void>[] = [];
  if (persistRemote) tasks.push(persistUiLocaleToApi(locale));
  if (syncTts) tasks.push(syncTtsDefaultLanguage(locale));
  if (tasks.length) await Promise.all(tasks);
}
