/**
 * Translations for Hebrew *values* inside cells, offered per column.
 *
 * This is display-only and strictly opt-in: filtering, sorting, grouping and export all
 * continue to use the stored value, because that is what the database holds. A value the
 * dictionary doesn't know is shown unchanged rather than guessed at.
 *
 * Two layers, checked in order:
 *   PHRASES - the whole cell value matches exactly (fuel types, ownership, "unknown").
 *   WORDS   - the value is split into tokens and each is looked up, which covers the
 *             combinatorial columns: colours ("כסף מטלי" -> silver metallic) and
 *             manufacturers ("טויוטה יפן" -> Toyota Japan).
 */

interface Term {
  ar: string;
  en: string;
}

const PHRASES: Record<string, Term> = {
  // fuel type (sug_delek_nm)
  'בנזין': { ar: "بنزين", en: "Petrol" },
  'דיזל': { ar: "ديزل", en: "Diesel" },
  'חשמל': { ar: "كهرباء", en: "Electric" },
  'חשמל/בנזין': { ar: "كهرباء/بنزين", en: "Electric/Petrol" },
  'חשמל/דיזל': { ar: "كهرباء/ديزل", en: "Electric/Diesel" },
  'גפמ"': { ar: "غاز مسال", en: "LPG" },

  // ownership (baalut)
  'פרטי': { ar: "خصوصي", en: "Private" },
  'ליסינג': { ar: "تأجير تمويلي", en: "Leasing" },
  'חברה': { ar: "شركة", en: "Company" },
  'סוחר': { ar: "تاجر", en: "Dealer" },
  'השכרה': { ar: "تأجير", en: "Rental" },

  // multi-word colour values that don't read well token by token
  'לא ידוע': { ar: "غير معروف", en: "Unknown" },
  'שן פיל': { ar: "عاجي", en: "Ivory" },
};

const WORDS: Record<string, Term> = {
  // --- colours (tzeva_rechev) ---
  'לבן': { ar: "أبيض", en: "White" },
  'שחור': { ar: "أسود", en: "Black" },
  'אפור': { ar: "رمادي", en: "Grey" },
  'כסף': { ar: "فضي", en: "Silver" },
  'כסוף': { ar: "فضي", en: "Silver" },
  'שנהב': { ar: "عاجي", en: "Ivory" },
  'כחול': { ar: "أزرق", en: "Blue" },
  'אדום': { ar: "أحمر", en: "Red" },
  'ירוק': { ar: "أخضر", en: "Green" },
  'צהוב': { ar: "أصفر", en: "Yellow" },
  'חום': { ar: "بني", en: "Brown" },
  'כתום': { ar: "برتقالي", en: "Orange" },
  'סגול': { ar: "بنفسجي", en: "Purple" },
  'ורוד': { ar: "وردي", en: "Pink" },
  'תכלת': { ar: "سماوي", en: "Light blue" },
  'בז': { ar: "بيج", en: "Beige" },
  'קרם': { ar: "كريمي", en: "Cream" },
  'זהב': { ar: "ذهبي", en: "Gold" },
  'ברונזה': { ar: "برونزي", en: "Bronze" },
  'פלדה': { ar: "فولاذي", en: "Steel" },
  'פנינה': { ar: "لؤلؤي", en: "Pearl" },
  'טורקיז': { ar: "تركوازي", en: "Turquoise" },
  'בורדו': { ar: "خمري", en: "Burgundy" },
  'קפה': { ar: "بني داكن", en: "Coffee" },
  'מטלי': { ar: "ميتاليك", en: "Metallic" },
  'מטאלי': { ar: "ميتاليك", en: "Metallic" },
  'מטל': { ar: "ميتاليك", en: "Metallic" },
  'מתכתי': { ar: "معدني", en: "Metallic" },
  'כהה': { ar: "غامق", en: "Dark" },
  'בהיר': { ar: "فاتح", en: "Light" },
  'פלטינה': { ar: "بلاتيني", en: "Platinum" },
  'ירקרק': { ar: "مخضر", en: "Greenish" },
  'כחלחל': { ar: "مزرق", en: "Bluish" },
  'אדמדם': { ar: "محمر", en: "Reddish" },
  'זהוב': { ar: "ذهبي", en: "Golden" },
  'זית': { ar: "زيتوني", en: "Olive" },
  'פחם': { ar: "فحمي", en: "Charcoal" },
  'חציל': { ar: "باذنجاني", en: "Aubergine" },
  'נחושת': { ar: "نحاسي", en: "Copper" },
  'קריסטל': { ar: "كريستالي", en: "Crystal" },
  'ים': { ar: "بحري", en: "Sea" },
  'לימון': { ar: "ليموني", en: "Lemon" },
  'רוז': { ar: "وردي", en: "Rose" },
  'מט': { ar: "مطفي", en: "Matte" },
  'מנדרינה': { ar: "مندريني", en: "Mandarin" },
  'חרדל': { ar: "خردلي", en: "Mustard" },
  'מילניום': { ar: "ميلينيوم", en: "Millennium" },
  'קלאסי': { ar: "كلاسيكي", en: "Classic" },
  'סהרה': { ar: "صحراوي", en: "Sahara" },
  'אקווה': { ar: "أكوا", en: "Aqua" },
  'זוהר': { ar: "لامع", en: "Bright" },
  'טוניק': { ar: "تونيك", en: "Tonic" },
  'מלאנג': { ar: "ميلانج", en: "Melange" },
  'חזק': { ar: "قوي", en: "Deep" },
  'יין': { ar: "نبيذي", en: "Wine" },
  'רב': { ar: "متعدد", en: "Multi" },
  'גווני': { ar: "الألوان", en: "colour" },

  // --- manufacturers (tozeret_nm) ---
  'טויוטה': { ar: "تويوتا", en: "Toyota" },
  'יונדאי': { ar: "هيونداي", en: "Hyundai" },
  'קיה': { ar: "كيا", en: "Kia" },
  'מזדה': { ar: "مازدا", en: "Mazda" },
  'סקודה': { ar: "سكودا", en: "Skoda" },
  'מיצובישי': { ar: "ميتسوبيشي", en: "Mitsubishi" },
  'ניסאן': { ar: "نيسان", en: "Nissan" },
  'סיאט': { ar: "سيات", en: "Seat" },
  'סוזוקי': { ar: "سوزوكي", en: "Suzuki" },
  'רנו': { ar: "رينو", en: "Renault" },
  'סובארו': { ar: "سوبارو", en: "Subaru" },
  'שברולט': { ar: "شفروليه", en: "Chevrolet" },
  'פולקסווגן': { ar: "فولكسفاغن", en: "Volkswagen" },
  "צ'רי": { ar: "شيري", en: "Chery" },
  'סיטרואן': { ar: "ستروين", en: "Citroen" },
  'לקסוס': { ar: "لكزس", en: "Lexus" },
  'הונדה': { ar: "هوندا", en: "Honda" },
  'פורד': { ar: "فورد", en: "Ford" },
  'אאודי': { ar: "أودي", en: "Audi" },
  'פיאט': { ar: "فيات", en: "Fiat" },
  'פיג׳ו': { ar: "بيجو", en: "Peugeot" },
  'מרצדס': { ar: "مرسيدس", en: "Mercedes" },
  'אופל': { ar: "أوبل", en: "Opel" },
  'וולוו': { ar: "فولفو", en: "Volvo" },
  'וולבו': { ar: "فولفو", en: "Volvo" },
  'דייהטסו': { ar: "دايهاتسو", en: "Daihatsu" },
  'בנץ': { ar: "بنز", en: "Benz" },
  'פורשה': { ar: "بورشه", en: "Porsche" },
  'טסלה': { ar: "تسلا", en: "Tesla" },
  'איסוזו': { ar: "إيسوزو", en: "Isuzu" },
  'דאציה': { ar: "داتشيا", en: "Dacia" },
  'גילי': { ar: "جيلي", en: "Geely" },
  'קרייזלר': { ar: "كرايسلر", en: "Chrysler" },
  "ג'יפ": { ar: "جيب", en: "Jeep" },
  "ג'אקו": { ar: "جاكوار", en: "Jaguar" },
  "ג'אק": { ar: "جاك", en: "JAC" },
  'מרוטי': { ar: "ماروتي", en: "Maruti" },
  'אקספנג': { ar: "إكسبنغ", en: "Xpeng" },
  'מ.ג': { ar: "إم جي", en: "MG" },
  "לנצ'יה": { ar: "لانشيا", en: "Lancia" },
  'קופרה': { ar: "كوبرا", en: "Cupra" },
  "דודג'": { ar: "دودج", en: "Dodge" },
  'סמארט': { ar: "سمارت", en: "Smart" },
  "פיאג'ו": { ar: "بياجيو", en: "Piaggio" },
  "ג'י.אמ.סי": { ar: "جي إم سي", en: "GMC" },
  "ג'יי.אמ.סי": { ar: "جي إم سي", en: "GMC" },

  // --- countries of manufacture ---
  'יפן': { ar: "اليابان", en: "Japan" },
  'קוריאה': { ar: "كوريا", en: "Korea" },
  'ד.קוריא': { ar: "كوريا الجنوبية", en: "South Korea" },
  'טורקיה': { ar: "تركيا", en: "Turkey" },
  "צ'כיה": { ar: "التشيك", en: "Czechia" },
  'ספרד': { ar: "إسبانيا", en: "Spain" },
  'סין': { ar: "الصين", en: "China" },
  'צרפת': { ar: "فرنسا", en: "France" },
  'אנגליה': { ar: "إنجلترا", en: "England" },
  'סלובקיה': { ar: "سلوفاكيا", en: "Slovakia" },
  'גרמניה': { ar: "ألمانيا", en: "Germany" },
  'גרמנ': { ar: "ألمانيا", en: "Germany" },
  'הונגריה': { ar: "المجر", en: "Hungary" },
  'תאילנד': { ar: "تايلاند", en: "Thailand" },
  'איטליה': { ar: "إيطاليا", en: "Italy" },
  'ארה"ב': { ar: "أمريكا", en: "USA" },
  'הודו': { ar: "الهند", en: "India" },
  'רומניה': { ar: "رومانيا", en: "Romania" },
  'פולין': { ar: "بولندا", en: "Poland" },
  'בלגיה': { ar: "بلجيكا", en: "Belgium" },
  'ברזיל': { ar: "البرازيل", en: "Brazil" },
  'מקסיקו': { ar: "المكسيك", en: "Mexico" },
  'רוסיה': { ar: "روسيا", en: "Russia" },
  'אוסטריה': { ar: "النمسا", en: "Austria" },
  'הולנד': { ar: "هولندا", en: "Netherlands" },
  'שבדיה': { ar: "السويد", en: "Sweden" },
  'ישראל': { ar: "إسرائيل", en: "Israel" },
  // the file truncates several country names, so the abbreviations need entries too
  'ארהב': { ar: "أمريكا", en: "USA" },
  'ארהב"': { ar: "أمريكا", en: "USA" },
  'הונג': { ar: "المجر", en: "Hungary" },
  'תאילנ': { ar: "تايلاند", en: "Thailand" },
  'מכסיקו': { ar: "المكسيك", en: "Mexico" },
  'מכסי': { ar: "المكسيك", en: "Mexico" },
  'מקסי': { ar: "المكسيك", en: "Mexico" },
  'אוסט': { ar: "النمسا", en: "Austria" },
  'פינל': { ar: "فنلندا", en: "Finland" },
  'בריטניה': { ar: "بريطانيا", en: "Britain" },
  'תורכיה': { ar: "تركيا", en: "Turkey" },
  'פורטוגל': { ar: "البرتغال", en: "Portugal" },
  'קנדה': { ar: "كندا", en: "Canada" },
  'ד.אפ': { ar: "جنوب أفريقيا", en: "South Africa" },
};

const HEBREW_RE = /[֐-׿]/;

/** Whether a string contains Hebrew letters at all. */
export function hasHebrew(value: string): boolean {
  return HEBREW_RE.test(value);
}

function pick(term: Term, language: string): string {
  return language.startsWith("ar") ? term.ar : term.en;
}

/**
 * Returns the translated value, or the original when it cannot be translated *in full*.
 *
 * All-or-nothing is deliberate: translating only the tokens we happen to know produces
 * values like "مرسيدس בנץ הונג", which is harder to read than either language alone.
 * A value is rendered in the target language only when every Hebrew token in it is
 * known; otherwise it is left exactly as stored.
 *
 * Separators (space, slash, hyphen, parentheses) are preserved so compound values keep
 * their shape: "כסף מטלי" -> "فضي ميتاليك", "סוזוקי-יפן" -> "سوزوكي-اليابان".
 */
export function translateValue(value: string, language: string): string {
  const trimmed = value.trim();
  if (!trimmed || !HEBREW_RE.test(trimmed)) return value;

  const phrase = PHRASES[trimmed];
  if (phrase) return pick(phrase, language);

  const parts = trimmed.split(/([\s/\-()]+)/);
  const out: string[] = [];
  for (const part of parts) {
    const term = WORDS[part] ?? PHRASES[part];
    if (term) {
      out.push(pick(term, language));
    } else if (HEBREW_RE.test(part)) {
      return value; // an unknown Hebrew token - leave the whole value alone
    } else {
      out.push(part); // separator, digit or Latin fragment: keep as-is
    }
  }
  return out.join("");
}
