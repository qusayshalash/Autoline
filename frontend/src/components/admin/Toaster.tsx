import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

import { IconAlert, IconCheckCircle, IconInfo } from "./AdminIcons";

/**
 * Transient confirmation for actions that finish somewhere other than where you clicked.
 *
 * The panels this replaces reported results by leaving a line of text behind inside
 * themselves, which is invisible if the result arrives after you have scrolled on - and
 * a backup takes minutes. A toast is the same information at a place the eye can find.
 *
 * Errors still also render inline where they happened; a toast is not a substitute for
 * saying which control failed.
 */

type ToastKind = "success" | "error" | "info";
type Toast = { id: number; kind: ToastKind; text: string };

const ToastContext = createContext<((kind: ToastKind, text: string) => void) | null>(null);

const LIFETIME_MS = 4200;

export function Toaster({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const push = useCallback((kind: ToastKind, text: string) => {
    const id = nextId.current++;
    setToasts((all) => [...all, { id, kind, text }]);
    window.setTimeout(() => setToasts((all) => all.filter((x) => x.id !== id)), LIFETIME_MS);
  }, []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="set-toasts" aria-live="polite" aria-atomic="false">
        {toasts.map((x) => (
          <div key={x.id} className={`set-toast ${x.kind}`} role="status">
            {x.kind === "success" ? (
              <IconCheckCircle />
            ) : x.kind === "error" ? (
              <IconAlert />
            ) : (
              <IconInfo />
            )}
            <span>{x.text}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/** Returns a no-op outside a Toaster, so a section can be rendered on its own in a test
 *  without the caller having to provide the provider. */
export function useToast() {
  return useContext(ToastContext) ?? (() => undefined);
}
