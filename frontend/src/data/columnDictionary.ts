import type { SemanticIconName } from "../components/SemanticIcons";
import { RAW_HEADER_LANGS } from "../i18n";

/**
 * Display metadata for column names the app recognises.
 *
 * The app ingests arbitrary CSVs, so this is a *lookup*, never a requirement: a column
 * that isn't listed here keeps its raw header and gets an icon derived from its data
 * type instead. Nothing here affects querying - sorting, filtering, cleaning and export
 * all address columns by their real name. This only changes what the user reads.
 *
 * The entries below cover the Israeli vehicle-registry export currently in use. Add
 * more datasets by extending this map; no other file needs to change.
 */
export interface ColumnMeta {
  ar: string;
  en: string;
  icon: SemanticIconName;
}

export const COLUMN_DICTIONARY: Record<string, ColumnMeta> = {
  mispar_rechev: { ar: "رقم المركبة", en: "Vehicle number", icon: "hash" },
  tozeret_cd: { ar: "رمز الصانع", en: "Manufacturer code", icon: "factory" },
  tozeret_nm: { ar: "الشركة المصنّعة", en: "Manufacturer", icon: "factory" },
  sug_degem: { ar: "نوع الطراز", en: "Model type", icon: "car" },
  degem_cd: { ar: "رمز الطراز", en: "Model code", icon: "car" },
  degem_nm: { ar: "اسم الطراز", en: "Model name", icon: "car" },
  kinuy_mishari: { ar: "الاسم التجاري", en: "Trade name", icon: "car" },
  ramat_gimur: { ar: "مستوى التجهيز", en: "Trim level", icon: "star" },
  ramat_eivzur_betihuty: { ar: "مستوى تجهيزات الأمان", en: "Safety equipment level", icon: "shield" },
  shnat_yitzur: { ar: "سنة الصنع", en: "Year of manufacture", icon: "calendar" },
  degem_manoa: { ar: "طراز المحرك", en: "Engine model", icon: "engine" },
  mivchan_acharon_dt: { ar: "تاريخ آخر فحص", en: "Last test date", icon: "calendar" },
  tokef_dt: { ar: "تاريخ انتهاء الترخيص", en: "Licence expiry", icon: "calendar" },
  moed_aliya_lakvish: { ar: "تاريخ النزول للشارع", en: "First on road", icon: "road" },
  baalut: { ar: "نوع الملكية", en: "Ownership", icon: "key" },
  misgeret: { ar: "رقم الشاصي", en: "Chassis number", icon: "barcode" },
  tzeva_cd: { ar: "رمز اللون", en: "Colour code", icon: "palette" },
  tzeva_rechev: { ar: "لون المركبة", en: "Vehicle colour", icon: "palette" },
  zmig_kidmi: { ar: "الإطار الأمامي", en: "Front tyre", icon: "tyre" },
  zmig_ahori: { ar: "الإطار الخلفي", en: "Rear tyre", icon: "tyre" },
  sug_delek_nm: { ar: "نوع الوقود", en: "Fuel type", icon: "fuel" },
  horaat_rishum: { ar: "أمر التسجيل", en: "Registration order", icon: "doc" },
  kvutzat_zihum: { ar: "مجموعة التلوث", en: "Pollution group", icon: "leaf" },
};

export function columnMeta(column: string): ColumnMeta | undefined {
  return COLUMN_DICTIONARY[column];
}

/** The name to show for a column: the dictionary label in the active language, or the
 *  raw header when the column isn't recognised - or when the active language asks for
 *  the file's own headers untouched (see RAW_HEADER_LANGS). */
export function columnLabel(column: string, language: string): string {
  if (RAW_HEADER_LANGS.has(language.split("-")[0])) return column;
  const meta = COLUMN_DICTIONARY[column];
  if (!meta) return column;
  return language.startsWith("ar") ? meta.ar : meta.en;
}

/** Whether the interpretation layer (translated names, meaning-based icons) applies at
 *  all in this language. */
export function usesRawHeaders(language: string): boolean {
  return RAW_HEADER_LANGS.has(language.split("-")[0]);
}
