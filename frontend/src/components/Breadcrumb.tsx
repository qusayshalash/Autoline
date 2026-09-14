import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

export interface BreadcrumbItem {
  label: string;
  to?: string;
}

export default function Breadcrumb({ items }: { items: BreadcrumbItem[] }) {
  const { t } = useTranslation();
  return (
    <nav className="breadcrumb" aria-label={t("nav.breadcrumb") ?? ""}>
      {items.map((item, i) => (
        <span key={i} className="breadcrumb-item">
          {item.to ? (
            <Link to={item.to}>{item.label}</Link>
          ) : (
            <span className={i === items.length - 1 ? "breadcrumb-current" : undefined}>{item.label}</span>
          )}
          {i < items.length - 1 && <span className="breadcrumb-sep">·</span>}
        </span>
      ))}
    </nav>
  );
}
