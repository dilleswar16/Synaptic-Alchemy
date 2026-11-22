import i18n, { type BackendModule, type ReadCallback } from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";
import { updatePreferences } from "@/api/authApi";
import { authBridge } from "@/auth/authBridge";

/**
 * Localisation (doc 01 §14). Namespaced JSON files under `./locales/<locale>/<namespace>.json` are loaded lazily
 * per namespace, so a feature's strings only download when its page renders.
 *
 * Add a namespace: create `locales/en/<namespace>.json` (plus `{}` placeholders for other locales) and add the
 * name to `translationNamespaces`. Use it with `useTranslation("<namespace>")`.
 */

export const supportedLocales = ["en", "ja", "zh-CN", "es", "es-MX", "nl", "fr"] as const;
export type SupportedLocale = (typeof supportedLocales)[number];

/** Autonyms: each language is listed in its own language, whatever the current UI language is. */
export const localeDisplayNames: Record<SupportedLocale, string> = {
  en: "English",
  ja: "日本語",
  "zh-CN": "简体中文",
  es: "Español",
  "es-MX": "Español (México)",
  nl: "Nederlands",
  fr: "Français",
};

export const translationNamespaces = [
  "common",
  "navigation",
  "auth",
  "home",
  "incidents",
  "investigations",
  "alerts",
  "slo",
  "intelligence",
  "metrics",
  "chat",
  "applications",
  "onboarding",
  "knowledge",
  "notifications",
  "administration",
] as const;
export type TranslationNamespace = (typeof translationNamespaces)[number];

const localeStorageKey = "keigan.locale";

const localeFileLoaders = import.meta.glob<{ default: Record<string, unknown> }>("./locales/*/*.json");

const lazyLocaleBackend: BackendModule = {
  type: "backend",
  init: () => undefined,
  read(language: string, namespace: string, callback: ReadCallback) {
    const loadLocaleFile = localeFileLoaders[`./locales/${language}/${namespace}.json`];
    if (!loadLocaleFile) {
      callback(null, {});
      return;
    }
    loadLocaleFile()
      .then((localeModule) => callback(null, localeModule.default))
      .catch((error: unknown) => callback(error instanceof Error ? error : new Error(String(error)), false));
  },
};

export function isSupportedLocale(value: unknown): value is SupportedLocale {
  return typeof value === "string" && (supportedLocales as readonly string[]).includes(value);
}

/** Maps browser codes onto supported locales: `ja-JP` → `ja`, `zh-Hans` → `zh-CN`, `es-AR` → `es`. */
export function normaliseLocale(languageCode: string): SupportedLocale {
  const lowerCaseCode = languageCode.toLowerCase();
  if (lowerCaseCode.startsWith("zh")) {
    return "zh-CN";
  }
  if (lowerCaseCode === "es-mx") {
    return "es-MX";
  }
  const exactMatch = supportedLocales.find((locale) => locale.toLowerCase() === lowerCaseCode);
  if (exactMatch) {
    return exactMatch;
  }
  const baseLanguage = lowerCaseCode.split("-")[0];
  return supportedLocales.find((locale) => locale === baseLanguage) ?? "en";
}

const localeFontFamilies: Partial<Record<SupportedLocale, string>> = {
  ja: "Noto+Sans+JP",
  "zh-CN": "Noto+Sans+SC",
};

/** Loads Noto Sans JP / SC only when a CJK locale is chosen (doc 04 §9). */
function loadLocaleFont(locale: SupportedLocale): void {
  const fontFamily = localeFontFamilies[locale];
  if (!fontFamily || document.querySelector(`link[data-locale-font="${locale}"]`)) {
    return;
  }
  const fontStylesheet = document.createElement("link");
  fontStylesheet.rel = "stylesheet";
  fontStylesheet.href = `https://fonts.googleapis.com/css2?family=${fontFamily}:wght@400;500;600;700&display=swap`;
  fontStylesheet.dataset.localeFont = locale;
  document.head.appendChild(fontStylesheet);
}

function applyDocumentLanguage(language: string): void {
  const locale = normaliseLocale(language);
  document.documentElement.lang = locale;
  document.documentElement.dir = "ltr";
  loadLocaleFont(locale);
}

i18n.on("languageChanged", applyDocumentLanguage);

export const i18nReady = i18n
  .use(lazyLocaleBackend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    supportedLngs: [...supportedLocales],
    nonExplicitSupportedLngs: false,
    load: "currentOnly",
    fallbackLng: {
      "es-MX": ["es", "en"],
      default: ["en"],
    },
    ns: ["common", "navigation", "auth"],
    defaultNS: "common",
    interpolation: {
      // React already escapes rendered strings.
      escapeValue: false,
    },
    detection: {
      order: ["localStorage", "navigator"],
      lookupLocalStorage: localeStorageKey,
      caches: ["localStorage"],
      convertDetectedLanguage: (detectedLanguage: string) => normaliseLocale(detectedLanguage),
    },
    react: {
      useSuspense: true,
    },
  });

export function currentSupportedLocale(): SupportedLocale {
  return normaliseLocale(i18n.resolvedLanguage ?? i18n.language ?? "en");
}

/**
 * Switches the UI language, remembers it in localStorage and — when signed in and `persistToProfile` is true —
 * saves it on the Keigan profile (failures ignored: the local choice already applies).
 */
export async function changeApplicationLanguage(locale: SupportedLocale, options: { persistToProfile?: boolean } = {}): Promise<void> {
  await i18n.changeLanguage(locale);
  if ((options.persistToProfile ?? true) && authBridge.isAuthenticated()) {
    updatePreferences({ preferredLocale: locale }).catch(() => undefined);
  }
}

export default i18n;
