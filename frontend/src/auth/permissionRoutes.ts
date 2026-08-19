/**
 * The first useful destination for a signed-in user. Keeping this in one place
 * avoids a custom role being sent to a route the interface will immediately deny.
 */
const ADMIN_DESTINATIONS = [
  ["system.view", "/admin"],
  ["users.view", "/admin/users"],
  ["roles.view", "/admin/roles"],
  ["languages.manage", "/admin/languages"],
  ["datasets.view", "/admin/files"],
  ["activity.view", "/admin/activity"],
] as const;

export const ADMIN_ACCESS_PERMISSIONS = [
  "system.view",
  "users.view",
  "roles.view",
  "languages.manage",
  "activity.view",
  "datasets.view",
] as const;

export function firstAllowedAdminPath(permissions: readonly string[]): string | null {
  const granted = new Set(permissions);
  return ADMIN_DESTINATIONS.find(([permission]) => granted.has(permission))?.[1] ?? null;
}

export function firstAllowedPath(permissions: readonly string[]): string {
  const granted = new Set(permissions);
  if (granted.has("datasets.view")) return "/";
  return firstAllowedAdminPath(permissions) ?? "/forbidden";
}
