import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { getMe, login as apiLogin, logout as apiLogout, type Role, type User } from "../api/client";

// A grant made in the roles screen must reach an already-open tab without a manual
// reload - this was hit live: a permission added on the server did not appear until the
// page was refreshed by hand. Revocation is the direction that matters more (a stale tab
// still showing a control the server will now reject), so this polls, re-checks on
// refocus, and re-checks immediately whenever any request comes back 403.
const REFRESH_INTERVAL_MS = 60_000;

function isUnauthorized(err: unknown): boolean {
  const status = (err as { response?: { status?: number } } | undefined)?.response?.status;
  return status === 401;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  hasRole: (...roles: Role[]) => boolean;
  /** true when the signed-in user's role grants every listed permission. Presentation
   *  only - the API enforces the same checks independently. */
  can: (...permissions: string[]) => boolean;
  /** true when the user holds at least one of the listed permissions */
  canAny: (...permissions: string[]) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  // Read inside the interval/listener closures without retriggering the effect that
  // sets them up every time the user object changes.
  const signedIn = useRef(false);

  useEffect(() => {
    getMe()
      .then((u) => {
        setUser(u);
        signedIn.current = true;
      })
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const refresh = useCallback(async () => {
    if (!signedIn.current) return; // nothing to keep in sync before the first sign-in
    try {
      setUser(await getMe());
    } catch (err) {
      // A network blip must not sign someone out from under them; only the server
      // actually saying the session is gone should.
      if (isUnauthorized(err)) {
        signedIn.current = false;
        setUser(null);
      }
    }
  }, []);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    window.addEventListener("focus", refresh);
    window.addEventListener("auth:forbidden", refresh);
    document.addEventListener("visibilitychange", onVisible);
    const id = window.setInterval(refresh, REFRESH_INTERVAL_MS);
    return () => {
      window.removeEventListener("focus", refresh);
      window.removeEventListener("auth:forbidden", refresh);
      document.removeEventListener("visibilitychange", onVisible);
      window.clearInterval(id);
    };
  }, [refresh]);

  async function login(username: string, password: string) {
    const u = await apiLogin(username, password);
    signedIn.current = true;
    setUser(u);
    return u;
  }

  async function logout() {
    await apiLogout();
    signedIn.current = false;
    setUser(null);
  }

  function hasRole(...roles: Role[]) {
    return !!user && roles.includes(user.role);
  }

  function can(...permissions: string[]) {
    const granted = new Set(user?.permissions ?? []);
    return permissions.every((p) => granted.has(p));
  }

  function canAny(...permissions: string[]) {
    const granted = new Set(user?.permissions ?? []);
    return permissions.some((p) => granted.has(p));
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, hasRole, can, canAny }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
