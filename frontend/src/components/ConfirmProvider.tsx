import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "./ConfirmDialog";

/**
 * Asking "are you sure?" without the browser's own dialog.
 *
 * window.confirm was doing this everywhere outside settings, and it is the wrong dialog
 * for this product: the browser draws it left-to-right, labels its buttons in the
 * operating system's language rather than the app's, and ignores the theme. The
 * question was translated; the box around it was not.
 *
 * It also blocks the main thread and is dismissed automatically by every test runner,
 * which quietly made each of those delete paths untestable.
 *
 * The promise-returning shape is deliberate. A dialog component would have every caller
 * keep its own "which row is pending" state, and the eight call sites this replaces read
 * as one line each:
 *
 *     if (await confirm({ body: t("datasets.confirm_delete") })) remove.mutate(id);
 *
 * which is the shape they already had.
 */

export type ConfirmOptions = {
  title?: string;
  body: string;
  confirmLabel?: string;
  /** Red confirm button and a warning icon. On by default: this is for deletions. */
  danger?: boolean;
};

type Ask = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<Ask | null>(null);

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [pending, setPending] = useState<ConfirmOptions | null>(null);
  const resolver = useRef<((answer: boolean) => void) | null>(null);

  const ask = useCallback<Ask>((options) => {
    setPending(options);
    return new Promise<boolean>((resolve) => {
      resolver.current = resolve;
    });
  }, []);

  const settle = useCallback((answer: boolean) => {
    setPending(null);
    resolver.current?.(answer);
    resolver.current = null;
  }, []);

  return (
    <ConfirmContext.Provider value={ask}>
      {children}
      <ConfirmDialog
        open={pending !== null}
        title={pending?.title ?? t("common.confirm_title")}
        body={pending?.body ?? ""}
        // Every caller so far is a deletion, so that is the default the button carries;
        // anything else states its own verb.
        confirmLabel={pending?.confirmLabel ?? t("common.delete")}
        danger={pending?.danger ?? true}
        onConfirm={() => settle(true)}
        onCancel={() => settle(false)}
      />
    </ConfirmContext.Provider>
  );
}

/**
 * Returns an `await`-able confirm.
 *
 * Outside a provider it answers false rather than throwing: refusing to render is a
 * worse failure than declining to delete, and a destructive action is the last thing
 * that should proceed because its dialog is missing.
 */
export function useConfirm(): Ask {
  const ask = useContext(ConfirmContext);
  return ask ?? (async () => false);
}
