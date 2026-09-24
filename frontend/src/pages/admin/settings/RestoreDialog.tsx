import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { RestoreDataset, RestorePlan } from "../../../api/admin";
import {
  fetchRestorePlan,
  fetchRestoreStatus,
  maintenanceStage,
  startRestore,
} from "../../../api/admin";
import { apiErrorMessage } from "../../../api/client";
import { IconAlert, IconRefresh } from "../../../components/admin/AdminIcons";
import { formatBytes, formatNumber } from "../../../data/numbers";
import { formatDateTime } from "../../../data/datetime";
import ErrorBanner from "../../../components/ErrorBanner";
import LoadingState from "../../../components/LoadingState";

const POLL_MS = 800;

/**
 * Restoring a backup, with what it would do said before it is done.
 *
 * The dialog is three screens in one, because a restore is three moments: deciding,
 * waiting, and finding out. The deciding screen is the one that matters - "restore" is a
 * word that sounds like it only adds things back, and the truth is that the catalog holds
 * the accounts and the activity log as well as the dataset list, so a restore is also a
 * deletion of everything since. The datasets that would disappear are listed by name, the
 * account counts are given as a before and after, and the confirm button stays disabled
 * until a checkbox says the person read it.
 *
 * The waiting screen reads its progress out of the server's refusals. During the swap
 * every endpoint answers 503 with the stage, so a poll that fails is the normal case and
 * a poll that succeeds means the swap is over.
 */
export default function RestoreDialog({
  name,
  onClose,
  onFinished,
}: {
  name: string;
  onClose: () => void;
  onFinished: () => void;
}) {
  const { t, i18n } = useTranslation();

  const [plan, setPlan] = useState<RestorePlan | null>(null);
  const [understood, setUnderstood] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stage, setStage] = useState<string | null>(null);
  const [done, setDone] = useState<{ ok: boolean; error: string; kept: string } | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    let alive = true;
    fetchRestorePlan(name)
      .then((p) => alive && setPlan(p))
      .catch((e) => alive && setError(apiErrorMessage(e, t("common.error_generic"))));
    return () => {
      alive = false;
    };
  }, [name, t]);

  // the poll is the only thing that has to be cleaned up: the restore itself is running
  // on the server and closing this dialog does not stop it
  useEffect(
    () => () => {
      if (timer.current) window.clearInterval(timer.current);
    },
    []
  );

  // Escape closes it while there is still a decision to make, and does nothing once the
  // restore has started: there is no cancelling a swap halfway, and a key that looked
  // like it might would be worse than one that does not answer.
  useEffect(() => {
    const deciding = stage === null && done === null;
    if (!deciding) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [stage, done, onClose]);

  async function begin() {
    setError(null);
    setStage("checking");
    try {
      await startRestore(name);
    } catch (e) {
      setStage(null);
      setError(apiErrorMessage(e, t("common.error_generic")));
      return;
    }
    timer.current = window.setInterval(async () => {
      try {
        const s = await fetchRestoreStatus();
        if (s.active) {
          setStage(s.stage);
          return;
        }
        if (!s.finished_at) return; // the worker has not picked it up yet
        if (timer.current) window.clearInterval(timer.current);
        timer.current = null;
        setStage(null);
        setDone({ ok: s.ok === true, error: s.error, kept: s.pre_restore_dir });
      } catch (e) {
        // a 503 here is the restore working, not a failure: it carries the stage
        const carried = maintenanceStage(e);
        if (carried !== null) {
          setStage(carried || "swapping");
          return;
        }
        // anything else during the swap is most likely the session ending with the
        // signing key, which is the expected outcome rather than an error
        setStage((current) => current ?? "swapping");
      }
    }, POLL_MS);
  }

  const blocked = (plan?.blockers.length ?? 0) > 0;
  const running = stage !== null;

  return (
    <div className="set-dialog-backdrop" role="presentation">
      <div
        className="set-dialog restore-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-label={t("admin.restore.title")}
      >
        <div className={`set-dialog-icon ${done?.ok ? "normal" : "danger"}`}>
          {done?.ok ? <IconRefresh /> : <IconAlert />}
        </div>

        {done ? (
          <Finished
            ok={done.ok}
            error={done.error}
            kept={done.kept}
            onClose={() => {
              onFinished();
              onClose();
            }}
          />
        ) : running ? (
          <Running stage={stage} />
        ) : (
          <>
            <h3>{t("admin.restore.title")}</h3>
            <p className="restore-lead">
              {t("admin.restore.lead", {
                when: plan?.created_at
                  ? formatDateTime(plan.created_at, i18n.language)
                  : name,
              })}
            </p>

            <ErrorBanner message={error} />

            {!plan ? (
              <LoadingState />
            ) : (
              <div className="restore-body">
                {blocked && (
                  <ul className="restore-blockers">
                    {plan.blockers.map((b) => (
                      <li key={b}>{t(`admin.restore.blocked.${b}`)}</li>
                    ))}
                  </ul>
                )}

                {/* The count is left out of these headings on purpose. The list is
                    directly under each one, so a number there would be the same fact
                    twice - and saying it in Arabic properly would mean six plural forms
                    for a figure the reader can see. */}
                <Group
                  tone="danger"
                  title={t("admin.restore.will_remove")}
                  rows={plan.datasets_removed}
                  value={(d) => fmt(d.rows_now)}
                />
                <Group
                  tone="good"
                  title={t("admin.restore.will_return")}
                  rows={plan.datasets_restored}
                  value={(d) => fmt(d.rows_in_backup)}
                />
                <Group
                  tone="warn"
                  title={t("admin.restore.will_change")}
                  rows={plan.datasets_changed}
                                  // said in words rather than with an arrow: an arrow points the wrong
                  // way once the page is right-to-left, and there is no one glyph that
                  // is correct in both directions
                  value={(d) =>
                    t("admin.restore.becomes", {
                      from: fmt(d.rows_now),
                      to: fmt(d.rows_in_backup),
                    })
                  }
                />

                <ul className="restore-facts">
                  <li>
                    {t("admin.restore.accounts", {
                      now: fmt(plan.users_now),
                      then:
                        plan.users_in_backup === null
                          ? "?"
                          : fmt(plan.users_in_backup),
                    })}
                  </li>
                  {plan.ends_sessions && <li>{t("admin.restore.sessions_end")}</li>}
                  {!plan.include_originals && <li>{t("admin.restore.no_originals")}</li>}
                  <li>
                    {t("admin.restore.kept_at")}{" "}
                    <bdi className="set-path">{plan.pre_restore_dir}</bdi>
                  </li>
                  <li>
                    {t("admin.restore.size", { size: formatBytes(plan.total_bytes, i18n.language) })}
                  </li>
                </ul>

                {!blocked && (
                  <label className="restore-check">
                    <input
                      type="checkbox"
                      checked={understood}
                      onChange={(e) => setUnderstood(e.target.checked)}
                    />
                    <span>{t("admin.restore.understood")}</span>
                  </label>
                )}
              </div>
            )}

            <div className="set-dialog-actions">
              <button type="button" className="set-btn secondary" onClick={onClose}>
                {t("common.cancel")}
              </button>
              <button
                type="button"
                className="set-btn danger-solid"
                disabled={!plan || blocked || !understood}
                onClick={begin}
              >
                {t("admin.restore.confirm")}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );

  function fmt(n: number): string {
    return formatNumber(n, i18n.language);
  }
}

function Group({
  tone,
  title,
  rows,
  value,
}: {
  tone: "danger" | "good" | "warn";
  title: string;
  rows: RestoreDataset[];
  value: (row: RestoreDataset) => string;
}) {
  if (rows.length === 0) return null;
  return (
    <div className={`restore-group stripe-${tone}`}>
      <h4>{title}</h4>
      <ul>
        {rows.map((d) => (
          <li key={d.dataset_id}>
            <bdi>{d.name}</bdi>
            <span className="num">{value(d)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The stages the server reports, in the order they happen. */
const STAGES = ["checking", "staging", "verifying", "closing", "swapping", "undoing", "reopening"];

function Running({ stage }: { stage: string }) {
  const { t } = useTranslation();
  const at = Math.max(0, STAGES.indexOf(stage));
  return (
    <>
      <h3>{t("admin.restore.running_title")}</h3>
      <p className="restore-lead">{t("admin.restore.running_warning")}</p>
      <ol className="restore-stages">
        {STAGES.filter((s) => s !== "undoing").map((s, i) => (
          <li key={s} className={i < at ? "past" : i === at ? "now" : ""}>
            {t(`admin.restore.stage.${s}`)}
          </li>
        ))}
      </ol>
    </>
  );
}

function Finished({
  ok,
  error,
  kept,
  onClose,
}: {
  ok: boolean;
  error: string;
  kept: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      <h3>{ok ? t("admin.restore.done_title") : t("admin.restore.failed_title")}</h3>
      <p className="restore-lead">
        {ok ? t("admin.restore.done_body") : t("admin.restore.failed_body")}
      </p>
      {!ok && error && (
        <p className="restore-error">
          <bdi>{error}</bdi>
        </p>
      )}
      {kept && (
        <p className="restore-lead">
          {t("admin.restore.kept_at")} <bdi className="set-path">{kept}</bdi>
        </p>
      )}
      <div className="set-dialog-actions">
        <button
          type="button"
          className="set-btn primary"
          onClick={() => {
            // a full reload rather than a route change: the accounts, the roles and the
            // signing key all just changed underneath the app, and every cached query in
            // it describes a database that no longer exists
            if (ok) window.location.reload();
            else onClose();
          }}
        >
          {ok ? t("admin.restore.reload") : t("common.close")}
        </button>
      </div>
    </>
  );
}
