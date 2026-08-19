import { useTranslation } from "react-i18next";

import { apiErrorMessage } from "../api/client";
import LoadingState from "./LoadingState";

interface Props {
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
}

/**
 * The three states a screen can be in before it has data: loading, failed, or ready.
 *
 * It exists because the obvious guard is wrong in a way that is hard to see:
 *
 *     if (isLoading || !data) return <LoadingState />
 *
 * That reads as "show a spinner until the data arrives", and it behaves that way as long
 * as the request succeeds. When it fails, `isLoading` goes false and `data` stays
 * undefined - so the same branch is taken and the spinner never stops. The screen tells
 * the user nothing is wrong while nothing is happening, which is worse than an error,
 * because there is nothing to act on and no reason to stop waiting.
 *
 * Rendering `null` when there is neither loading nor error is deliberate: the caller
 * still owns the ready state, so this drops in front of an existing component without
 * taking over its layout.
 */
export default function QueryState({ loading, error, onRetry }: Props) {
  const { t } = useTranslation();

  if (error) {
    return (
      <div className="query-error" role="alert">
        <p className="query-error-message">
          {apiErrorMessage(error, t("common.error_loading_data"))}
        </p>
        {onRetry && (
          <button type="button" className="btn secondary small" onClick={() => onRetry()}>
            {t("common.retry")}
          </button>
        )}
      </div>
    );
  }

  if (loading) return <LoadingState />;
  return null;
}
