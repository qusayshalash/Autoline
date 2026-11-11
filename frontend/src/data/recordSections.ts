/**
 * How a record's card groups its fields.
 *
 * A record from the registry is twenty-odd fields of very different weight: a make and
 * a model a person reads first, dates that say whether the vehicle is legal to drive,
 * tyre sizes somebody looks up once, and internal codes almost nobody reads at all. One
 * flat grid gave them all the same voice. Grouped, the card reads top to bottom the way
 * the questions come: what is it, is it licensed, what is in it, and the codes last.
 *
 * Like the column dictionary this is a lookup, never a requirement. A column not named
 * here lands in "other fields", and a file with none of these columns gets a single
 * plain section - the card works for any keyed file, it is only shaped for this one.
 */

export type SectionId = "vehicle" | "licence" | "technical" | "codes" | "other";

export const RECORD_SECTIONS: { id: Exclude<SectionId, "other">; columns: string[] }[] = [
  {
    id: "vehicle",
    columns: [
      "tozeret_nm",
      "kinuy_mishari",
      "degem_nm",
      "ramat_gimur",
      "shnat_yitzur",
      "tzeva_rechev",
      "sug_delek_nm",
    ],
  },
  {
    id: "licence",
    columns: ["baalut", "moed_aliya_lakvish", "mivchan_acharon_dt", "tokef_dt", "horaat_rishum"],
  },
  {
    id: "technical",
    columns: ["degem_manoa", "zmig_kidmi", "zmig_ahori", "kvutzat_zihum", "ramat_eivzur_betihuty"],
  },
  {
    id: "codes",
    columns: ["mispar_rechev", "misgeret", "tozeret_cd", "degem_cd", "sug_degem", "tzeva_cd"],
  },
];

/** The fields the card's heading is made of, when the file has them. */
export const HEADLINE = {
  make: "tozeret_nm",
  trade: "kinuy_mishari",
  model: "degem_nm",
  trim: "ramat_gimur",
  year: "shnat_yitzur",
  colour: "tzeva_rechev",
  fuel: "sug_delek_nm",
  ownership: "baalut",
  lastTest: "mivchan_acharon_dt",
  licenceUntil: "tokef_dt",
} as const;

/** Columns whose values are dates, shown as dates rather than as the file's text. */
export const DATE_COLUMNS = new Set(["mivchan_acharon_dt", "tokef_dt", "moed_aliya_lakvish"]);

/** Identifiers read character by character: set in tabular figures, left to right. */
export const CODE_COLUMNS = new Set([
  "mispar_rechev",
  "misgeret",
  "tozeret_cd",
  "degem_cd",
  "tzeva_cd",
  "degem_manoa",
  "zmig_kidmi",
  "zmig_ahori",
  "horaat_rishum",
]);
