/**
 * Vehicle manufacturers: how to recognise one in the data, and how to present it.
 *
 * This is a display layer, entirely separate from querying - nothing here ever reaches
 * SQL. Filtering still happens on the stored value, because the stored value is what the
 * database holds.
 *
 * Recognition has to work on the values as they actually are. In this registry the
 * manufacturer column pairs the maker with its country of assembly, in Hebrew:
 * "קיה קוריאה", "טויוטה יפן", "סקודה צ'כיה". So a value is tokenised and each token is
 * looked up; the country half simply doesn't match anything and is ignored. Latin
 * spellings are matched too, for datasets that store "KIA" plainly.
 *
 * `logo` points at /brands/<slug>.svg. Those files are not shipped - see
 * public/brands/README.md - and BrandLogo falls back to a coloured monogram when one is
 * missing, so the dashboard looks finished either way and gains real logos the moment
 * files are dropped in.
 */

export interface Brand {
  slug: string;
  ar: string;
  en: string;
  /** the marque's own colour, used for the logo tile and the brand card accent */
  color: string;
  /** tokens that identify this brand inside a cell value, Hebrew and Latin */
  tokens: string[];
}

export const BRANDS: Brand[] = [
  { slug: "toyota", ar: "تويوتا", en: "Toyota", color: "#c8102e", tokens: ["טויוטה", "TOYOTA"] },
  { slug: "hyundai", ar: "هيونداي", en: "Hyundai", color: "#002c5f", tokens: ["יונדאי", "HYUNDAI"] },
  { slug: "kia", ar: "كيا", en: "Kia", color: "#bb162b", tokens: ["קיה", "KIA"] },
  { slug: "mazda", ar: "مازدا", en: "Mazda", color: "#910a2d", tokens: ["מזדה", "MAZDA"] },
  { slug: "skoda", ar: "سكودا", en: "Škoda", color: "#0e3a2f", tokens: ["סקודה", "SKODA"] },
  { slug: "mitsubishi", ar: "ميتسوبيشي", en: "Mitsubishi", color: "#c00000", tokens: ["מיצובישי", "MITSUBISHI"] },
  { slug: "nissan", ar: "نيسان", en: "Nissan", color: "#c3002f", tokens: ["ניסאן", "NISSAN"] },
  { slug: "seat", ar: "سيات", en: "Seat", color: "#a6192e", tokens: ["סיאט", "SEAT"] },
  { slug: "suzuki", ar: "سوزوكي", en: "Suzuki", color: "#0a2b6b", tokens: ["סוזוקי", "SUZUKI"] },
  { slug: "renault", ar: "رينو", en: "Renault", color: "#3b3b3b", tokens: ["רנו", "RENAULT"] },
  { slug: "subaru", ar: "سوبارو", en: "Subaru", color: "#013c74", tokens: ["סובארו", "SUBARU"] },
  { slug: "chevrolet", ar: "شفروليه", en: "Chevrolet", color: "#8a6d1f", tokens: ["שברולט", "CHEVROLET"] },
  { slug: "volkswagen", ar: "فولكسفاغن", en: "Volkswagen", color: "#001e50", tokens: ["פולקסווגן", "VOLKSWAGEN", "VW"] },
  { slug: "chery", ar: "شيري", en: "Chery", color: "#b01f24", tokens: ["צ'רי", "צ׳רי", "CHERY"] },
  { slug: "citroen", ar: "ستروين", en: "Citroën", color: "#8b1a2b", tokens: ["סיטרואן", "CITROEN"] },
  { slug: "lexus", ar: "لكزس", en: "Lexus", color: "#1a1a1a", tokens: ["לקסוס", "LEXUS"] },
  { slug: "honda", ar: "هوندا", en: "Honda", color: "#cc0000", tokens: ["הונדה", "HONDA"] },
  { slug: "ford", ar: "فورد", en: "Ford", color: "#003478", tokens: ["פורד", "FORD"] },
  { slug: "audi", ar: "أودي", en: "Audi", color: "#bb0a30", tokens: ["אאודי", "AUDI"] },
  { slug: "fiat", ar: "فيات", en: "Fiat", color: "#8e1b32", tokens: ["פיאט", "FIAT"] },
  { slug: "peugeot", ar: "بيجو", en: "Peugeot", color: "#12283c", tokens: ["פיג׳ו", "פיג'ו", "PEUGEOT"] },
  { slug: "mercedes", ar: "مرسيدس", en: "Mercedes-Benz", color: "#1b1b1b", tokens: ["מרצדס", "בנץ", "MERCEDES", "BENZ"] },
  { slug: "opel", ar: "أوبل", en: "Opel", color: "#5a4a00", tokens: ["אופל", "OPEL"] },
  { slug: "volvo", ar: "فولفو", en: "Volvo", color: "#003057", tokens: ["וולוו", "וולבו", "VOLVO"] },
  { slug: "daihatsu", ar: "دايهاتسو", en: "Daihatsu", color: "#9e1b32", tokens: ["דייהטסו", "DAIHATSU"] },
  { slug: "porsche", ar: "بورشه", en: "Porsche", color: "#2b2b2b", tokens: ["פורשה", "PORSCHE"] },
  { slug: "tesla", ar: "تسلا", en: "Tesla", color: "#a01c23", tokens: ["טסלה", "TESLA"] },
  { slug: "isuzu", ar: "إيسوزو", en: "Isuzu", color: "#a4262c", tokens: ["איסוזו", "ISUZU"] },
  { slug: "dacia", ar: "داتشيا", en: "Dacia", color: "#1c4a3a", tokens: ["דאציה", "DACIA"] },
  { slug: "geely", ar: "جيلي", en: "Geely", color: "#1f4e79", tokens: ["גילי", "GEELY"] },
  { slug: "chrysler", ar: "كرايسلر", en: "Chrysler", color: "#1a3a5c", tokens: ["קרייזלר", "CHRYSLER"] },
  { slug: "jeep", ar: "جيب", en: "Jeep", color: "#2f4f2f", tokens: ["ג'יפ", "ג׳יפ", "JEEP"] },
  { slug: "jaguar", ar: "جاكوار", en: "Jaguar", color: "#1c3f33", tokens: ["ג'אקו", "ג׳אקו", "JAGUAR"] },
  { slug: "jac", ar: "جاك", en: "JAC", color: "#b02a30", tokens: ["ג'אק", "ג׳אק", "JAC"] },
  { slug: "maruti", ar: "ماروتي", en: "Maruti", color: "#0b4f8a", tokens: ["מרוטי", "MARUTI"] },
  { slug: "xpeng", ar: "إكسبنغ", en: "Xpeng", color: "#0f5c5c", tokens: ["אקספנג", "XPENG"] },
  { slug: "mg", ar: "إم جي", en: "MG", color: "#8b1e2d", tokens: ["מ.ג", "MG"] },
  { slug: "lancia", ar: "لانشيا", en: "Lancia", color: "#1b3a6b", tokens: ["לנצ'יה", "לנצ׳יה", "LANCIA"] },
  { slug: "cupra", ar: "كوبرا", en: "Cupra", color: "#8a5a2b", tokens: ["קופרה", "CUPRA"] },
  { slug: "dodge", ar: "دودج", en: "Dodge", color: "#8b1a1a", tokens: ["דודג'", "דודג׳", "DODGE"] },
  { slug: "smart", ar: "سمارت", en: "Smart", color: "#2e6e8e", tokens: ["סמארט", "SMART"] },
  { slug: "piaggio", ar: "بياجيو", en: "Piaggio", color: "#123c6b", tokens: ["פיאג'ו", "פיאג׳ו", "PIAGGIO"] },
  { slug: "gmc", ar: "جي إم سي", en: "GMC", color: "#a52a2a", tokens: ["ג'י.אמ.סי", "ג'יי.אמ.סי", "GMC"] },
  { slug: "byd", ar: "بي واي دي", en: "BYD", color: "#0d4f8b", tokens: ["בי.וואי.די", "BYD"] },
  { slug: "bmw", ar: "بي إم دبليو", en: "BMW", color: "#0066b1", tokens: ["ב.מ.וו", "במוו", "BMW"] },
];

/** token -> brand, built once. Tokens are compared case-insensitively. */
const BY_TOKEN = new Map<string, Brand>();
for (const brand of BRANDS) {
  for (const token of brand.tokens) BY_TOKEN.set(token.toUpperCase(), brand);
}

const SPLIT_RE = /[\s/\-.,()]+/;

/**
 * The brand a cell value refers to, or undefined when none is recognised.
 *
 * Matching is per token so the country half of "קיה קוריאה" is ignored, and the longest
 * token wins nothing special - brands here never share a token.
 */
export function brandFor(value: string | null | undefined): Brand | undefined {
  if (!value) return undefined;
  const trimmed = value.trim();
  if (!trimmed) return undefined;

  const direct = BY_TOKEN.get(trimmed.toUpperCase());
  if (direct) return direct;

  for (const part of trimmed.split(SPLIT_RE)) {
    const hit = BY_TOKEN.get(part.toUpperCase());
    if (hit) return hit;
  }
  return undefined;
}

export function brandName(brand: Brand, language: string): string {
  return language.startsWith("ar") ? brand.ar : brand.en;
}

/** Where a real logo file would live. BrandLogo probes this and falls back silently. */
export function brandLogoUrl(brand: Brand): string {
  return `/brands/${brand.slug}.svg`;
}
