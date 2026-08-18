import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { getMe, login as apiLogin, logout as apiLogout, type Role, type User } from "../api/client";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
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

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  async function login(username: string, password: string) {
    const u = await apiLogin(username, password);
    setUser(u);
  }

  async function logout() {
    await apiLogout();
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
