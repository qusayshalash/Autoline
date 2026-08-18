import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import ar from "./ar.json";
import en from "./en.json";
import he from "./he.json";

export const RTL_LANGS = new Set(["ar", "he"]);

/** Languages in which column headers are shown exactly as they appear in the source
 *  file, with no dictionary lookup. Hebrew is the language of these datasets' origin,
 *  so translating their headers would obscure rather than help. */
export const RAW_HEADER_LANGS = new Set(["he"]);

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      ar: { translation: ar },
      en: { translation: en },
      he: { translation: he },
    },
    fallbackLng: "ar",
    supportedLngs: ["ar", "en", "he"],
    interpolation: { escapeValue: false },
  });

export function applyDirection(lang: string) {
  const dir = RTL_LANGS.has(lang) ? "rtl" : "ltr";
  document.documentElement.dir = dir;
  document.documentElement.lang = lang;
}

i18n.on("languageChanged", (lng) => applyDirection(lng));
applyDirection(i18n.language || "ar");

export default i18n;
