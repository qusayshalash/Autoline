import { useTranslation } from "react-i18next";

import type { Brand } from "../../data/brandRegistry";
import { brandName } from "../../data/brandRegistry";
import BrandLogo from "./BrandLogo";
import { formatCount, formatPercent } from "./labels";

interface Props {
  brand?: Brand;
  /** the value as stored, shown when the marque isn't in the registry */
  rawValue: string;
  matched: number;
  grandTotal: number;
}

/**
 * The header shown when the filters narrow the file to a single manufacturer.
 *
 * Its job is to answer "how big is this maker here?" - the matching count, and what
 * share of the whole file that is. Both come from the same response the charts use, so
 * the card can never disagree with them.
 */
export default function BrandCard({ brand, rawValue, matched, grandTotal }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const name = brand ? brandName(brand, lang) : rawValue;
  const share = grandTotal > 0 ? (matched * 100) / grandTotal : 0;

  return (
    <section
      className="stats-brand-card"
      style={brand ? ({ "--brand": brand.color } as React.CSSProperties) : undefined}
    >
      <BrandLogo brand={brand} label={rawValue} size={52} />

      <div className="stats-brand-id">
        <h2>{t("statistics.brand_title", { brand: name })}</h2>
        <p title={rawValue}>{rawValue}</p>
      </div>

      <div className="stats-brand-figures">
        <div>
          <strong>{formatCount(matched, lang)}</strong>
          <small>{t("statistics.brand_total")}</small>
        </div>
        <div>
          <strong>{formatPercent(share, lang)}</strong>
          <small>{t("statistics.brand_share")}</small>
        </div>
      </div>
    </section>
  );
}
