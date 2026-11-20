import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { fetchSimilar, gridPath } from "../api/catalog";
import { formatNumber } from "../data/numbers";

const svg = {
  viewBox: "0 0 20 20",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

/** How many cars like this one the same file holds - the same make and model, and of
 *  those the same engine - each a link that opens exactly those rows in the grid. */
export default function SimilarVehicles({ datasetId, query }: { datasetId: string; query: string }) {
  const { t, i18n } = useTranslation();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["similar-vehicles", datasetId, query],
    queryFn: () => fetchSimilar(datasetId, query),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  if (isError || (data && !data.model)) return null;
  const n = (value: number) => formatNumber(value, i18n.language);
  const engineCode = data?.engine?.filters[data.engine.filters.length - 1]?.value;

  return (
    <section className="similar" aria-busy={isLoading}>
      <span className="similar-icon" aria-hidden="true">
        <IconCars />
      </span>
      <div className="similar-body">
        <strong>{t("catalog.similar_title")}</strong>
        {isLoading || !data?.model ? (
          <span className="similar-loading">{t("catalog.similar_counting")}</span>
        ) : (
          <div className="similar-links">
            {data.engine && (
              <Link to={gridPath(datasetId, data.engine.filters)} className="similar-link primary">
                <b>{n(data.engine.count)}</b>
                <span>
                  {t("catalog.similar_engine", { count: data.engine.count })}{" "}
                  <bdi className="similar-code" dir="ltr">
                    {engineCode}
                  </bdi>
                </span>
                <IconChevron />
              </Link>
            )}
            <Link to={gridPath(datasetId, data.model.filters)} className="similar-link">
              <b>{n(data.model.count)}</b>
              <span>{t("catalog.similar_model", { count: data.model.count })}</span>
              <IconChevron />
            </Link>
          </div>
        )}
      </div>
    </section>
  );
}

function IconCars() {
  return (
    <svg {...svg} width={20} height={20}>
      <path d="M2 14h11M3 14l1.3-3.4c.3-.7.9-1.1 1.6-1.1h3.2c.7 0 1.3.4 1.6 1.1L12 14" />
      <path d="M8 7.5l.9-2.3c.3-.7.9-1.2 1.7-1.2h3.2c.7 0 1.3.5 1.6 1.2L17 9.5M14.5 12H18" />
      <circle cx="5" cy="15.5" r="1.1" />
      <circle cx="10" cy="15.5" r="1.1" />
    </svg>
  );
}
function IconChevron() {
  // points onward along the line; turned for a right-to-left page in the stylesheet
  return (
    <svg {...svg} width={14} height={14} className="similar-chevron">
      <path d="M8 5l5 5-5 5" />
    </svg>
  );
}
