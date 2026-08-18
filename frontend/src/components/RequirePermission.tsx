import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

/**
 * Route guard by permission. This is a navigation convenience only - the API enforces
 * the same permissions on every request, so bypassing this gains nothing.
 */
export default function RequirePermission({
  children,
  all,
  any,
  redirectTo = "/",
}: {
  children: ReactNode;
  /** every permission listed is required */
  all?: string[];
  /** at least one of these is required */
  any?: string[];
  redirectTo?: string;
}) {
  const { loading, can, canAny } = useAuth();

  if (loading) return null;
  if (all && all.length > 0 && !can(...all)) return <Navigate to={redirectTo} replace />;
  if (any && any.length > 0 && !canAny(...any)) return <Navigate to={redirectTo} replace />;
  return <>{children}</>;
}
