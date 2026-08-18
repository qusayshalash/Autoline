import { api } from "./client";
import type { JobOut } from "./client";

export type UserStatus = "active" | "inactive" | "suspended" | "pending";

export interface AdminUser {
  id: string;
  username: string;
  full_name: string;
  email: string;
  role: string;
  status: UserStatus;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Permission {
  key: string;
  module: string;
  action: string;
}

export interface RoleSummary {
  slug: string;
  name: string;
  description: string;
  is_system: boolean;
  user_count: number;
  permission_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface RoleDetail extends RoleSummary {
  permissions: string[];
}

export interface ActivityItem {
  id: string;
  at: string | null;
  actor_id: string;
  actor_username: string;
  action: string;
  target_type: string;
  target_id: string;
  target_label: string;
  detail: string;
}

export interface Overview {
  users_total: number;
  users_active: number;
  users_by_status: Record<string, number>;
  roles_total: number;
  permissions_total: number;
  languages_enabled: number;
  files_total: number;
  files_bytes: number;
  files_rows: number;
  last_activity: ActivityItem | null;
}

export interface Language {
  code: string;
  name: string;
  native_name: string;
  direction: "rtl" | "ltr";
  enabled: boolean;
  is_default: boolean;
}

export interface SystemStatus {
  status: string;
  data_dir: string;
  storage_bytes: number;
  uploads_bytes: number;
  datasets_bytes: number;
  exports_bytes: number;
  dataset_count: number;
  started_at: string;
  uptime_seconds: number;
}

// ---- overview / system ----

export async function fetchOverview(): Promise<Overview> {
  const { data } = await api.get<Overview>("/admin/overview");
  return data;
}

export async function fetchSystemStatus(): Promise<SystemStatus> {
  const { data } = await api.get<SystemStatus>("/admin/system");
  return data;
}

// ---- activity ----

export async function fetchActivity(params: {
  limit?: number;
  offset?: number;
  action?: string | null;
  actor_id?: string | null;
}): Promise<{ items: ActivityItem[]; total: number }> {
  const { data } = await api.get<{ items: ActivityItem[]; total: number }>("/admin/activity", {
    params: {
      limit: params.limit ?? 50,
      offset: params.offset ?? 0,
      action: params.action || undefined,
      actor_id: params.actor_id || undefined,
    },
  });
  return data;
}

// ---- users ----

export async function fetchUsers(): Promise<AdminUser[]> {
  const { data } = await api.get<AdminUser[]>("/users");
  return data;
}

export async function createUser(body: {
  username: string;
  password: string;
  role: string;
  full_name?: string;
  email?: string;
  status?: UserStatus;
}): Promise<AdminUser> {
  const { data } = await api.post<AdminUser>("/users", body);
  return data;
}

export async function updateUser(
  id: string,
  body: Partial<{
    role: string;
    status: UserStatus;
    full_name: string;
    email: string;
    password: string;
  }>
): Promise<AdminUser> {
  const { data } = await api.patch<AdminUser>(`/users/${id}`, body);
  return data;
}

export async function deleteUser(id: string): Promise<void> {
  await api.delete(`/users/${id}`);
}

// ---- roles & permissions ----

export async function fetchPermissions(): Promise<Permission[]> {
  const { data } = await api.get<Permission[]>("/permissions");
  return data;
}

export async function fetchRoles(): Promise<RoleSummary[]> {
  const { data } = await api.get<RoleSummary[]>("/roles");
  return data;
}

export async function fetchRole(slug: string): Promise<RoleDetail> {
  const { data } = await api.get<RoleDetail>(`/roles/${slug}`);
  return data;
}

export async function createRole(body: {
  name: string;
  description?: string;
  permissions: string[];
}): Promise<RoleDetail> {
  const { data } = await api.post<RoleDetail>("/roles", body);
  return data;
}

export async function updateRole(
  slug: string,
  body: Partial<{ name: string; description: string; permissions: string[] }>
): Promise<RoleDetail> {
  const { data } = await api.patch<RoleDetail>(`/roles/${slug}`, body);
  return data;
}

export async function deleteRole(slug: string): Promise<void> {
  await api.delete(`/roles/${slug}`);
}

// ---- languages ----

export async function fetchLanguages(): Promise<Language[]> {
  const { data } = await api.get<Language[]>("/admin/languages");
  return data;
}

export async function updateLanguages(body: {
  enabled?: string[];
  default?: string;
}): Promise<Language[]> {
  const { data } = await api.patch<Language[]>("/admin/languages", body);
  return data;
}

// ---- storage ----

export interface StorageCategory {
  key: string;
  bytes: number;
  files: number;
  removable: boolean;
}

export interface StorageCandidate {
  path: string;
  category: string;
  bytes: number;
  modified: string;
  age_hours: number;
  reason: string;
}

export interface StorageOverview {
  data_dir: string;
  total_bytes: number;
  /** 0 means nothing expires on its own */
  retention_hours: number;
  suggested_retention_hours: number;
  categories: StorageCategory[];
  reclaimable_bytes: number;
  reclaimable_files: number;
  uploads_bytes: number;
  disk_free_bytes: number;
}

export interface CleanupOptions {
  expired_exports: boolean;
  all_exports: boolean;
  intermediates: boolean;
}

export async function fetchStorage(): Promise<StorageOverview> {
  const { data } = await api.get<StorageOverview>("/admin/storage");
  return data;
}

/** What a cleanup with these options would delete. Always called before offering the
 *  cleanup itself, so the list is on screen before anything is removed. */
export async function fetchCleanupPlan(options: CleanupOptions): Promise<StorageCandidate[]> {
  const { data } = await api.get<StorageCandidate[]>("/admin/storage/plan", { params: options });
  return data;
}

export async function runCleanup(
  options: CleanupOptions
): Promise<{ removed_files: number; freed_bytes: number; failed: string[] }> {
  const { data } = await api.post("/admin/storage/cleanup", options);
  return data;
}

export async function setRetention(hours: number): Promise<StorageOverview> {
  const { data } = await api.patch<StorageOverview>("/admin/storage/retention", { hours });
  return data;
}

// ---- backups ----

export interface BackupItem {
  kind: "catalog" | "dataset" | "key" | "original";
  file: string;
  bytes: number;
  dataset_id?: string | null;
  name: string;
  /** table name -> row count, as counted while snapshotting and again on read-back */
  tables: Record<string, number>;
}

export interface Backup {
  name: string;
  created_at: string;
  duration_s: number;
  include_originals: boolean;
  same_disk_as_data: boolean;
  total_bytes: number;
  bytes_on_disk: number;
  items: BackupItem[];
  /** every table was read back out of the written files and matched */
  verified: boolean;
  intact: boolean;
  errors: string[];
}

export interface BackupSummary {
  backup_dir: string;
  same_disk_as_data: boolean;
  keep: number;
  count: number;
  verified_count: number;
  total_bytes: number;
  latest_at: string;
  latest_verified: boolean;
  disk_free_bytes: number;
}

export async function fetchBackups(): Promise<Backup[]> {
  const { data } = await api.get<Backup[]>("/admin/backups");
  return data;
}

export async function fetchBackupSummary(): Promise<BackupSummary> {
  const { data } = await api.get<BackupSummary>("/admin/backups/summary");
  return data;
}

/** Starts a backup. It runs as a job - poll it with fetchJob. */
export async function startBackup(includeOriginals: boolean): Promise<JobOut> {
  const { data } = await api.post<JobOut>("/admin/backups", {
    include_originals: includeOriginals,
  });
  return data;
}

export async function deleteBackup(name: string): Promise<void> {
  await api.delete(`/admin/backups/${encodeURIComponent(name)}`);
}

export async function pruneBackups(): Promise<{ removed: number; freed_bytes: number }> {
  const { data } = await api.post<{ removed: number; freed_bytes: number }>(
    "/admin/backups/prune"
  );
  return data;
}

// ---- login lockouts ----

export interface Lockout {
  key: string;
  kind: "user" | "ip";
  subject: string;
  failures: number;
  first_failure_at: string;
  last_failure_at: string;
  locked_until: string;
  retry_after_s: number;
}

export async function fetchLockouts(): Promise<Lockout[]> {
  const { data } = await api.get<Lockout[]>("/admin/lockouts");
  return data;
}

export async function clearLockout(key: string): Promise<void> {
  await api.delete(`/admin/lockouts/${encodeURIComponent(key)}`);
}

// ---- compaction ----

export interface CompactionEstimate {
  dataset_id: string;
  file_bytes: number;
  tables: Record<string, number>;
}

export interface CompactionResult {
  dataset_id: string;
  bytes_before: number;
  bytes_after: number;
  freed_bytes: number;
  tables: Record<string, number>;
  duration_s: number;
  /** the file was already compact, and was left untouched */
  skipped: boolean;
  reason: string;
}

export async function fetchCompactionEstimate(datasetId: string): Promise<CompactionEstimate> {
  const { data } = await api.get<CompactionEstimate>(`/admin/datasets/${datasetId}/compaction`);
  return data;
}

/** Starts a compaction. It runs as a job - poll it with getJob. */
export async function startCompaction(datasetId: string): Promise<JobOut> {
  const { data } = await api.post<JobOut>(`/admin/datasets/${datasetId}/compaction`, {});
  return data;
}
