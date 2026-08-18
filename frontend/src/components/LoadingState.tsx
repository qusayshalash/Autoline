import { useTranslation } from "react-i18next";

export default function LoadingState() {
  const { t } = useTranslation();
  return (
    <div className="loading-state">
      <span className="spinner" aria-hidden="true" />
      <span>{t("common.loading")}</span>
    </div>
  );
}
