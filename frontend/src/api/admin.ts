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
  /** The English sentence the server composed. Shown when there is no code. */
  detail: string;
  /** The same detail as a translatable key, absent on entries written before it existed. */
  detail_code: string;
  detail_params: Record<string, unknown>;
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

// ---- activity trail ----

export interface ActivityPurgeResult {
  removed: number;
  remaining: number;
  cutoff: string;
}

/** What a purge at this cutoff would remove, without removing it. */
export async function fetchActivityPurgePlan(olderThanDays: number): Promise<ActivityPurgeResult> {
  const { data } = await api.get<ActivityPurgeResult>("/admin/activity/purge-plan", {
    params: { older_than_days: olderThanDays },
  });
  return data;
}

export async function purgeActivity(olderThanDays: number): Promise<ActivityPurgeResult> {
  const { data } = await api.post<ActivityPurgeResult>("/admin/activity/purge", {
    older_than_days: olderThanDays,
  });
  return data;
}

// ---- catalog housekeeping ----

export interface HousekeepingStatus {
  jobs_total: number;
  jobs_retention_days: number;
  jobs_due: number;
  /** Old export rows kept anyway, because their file is still downloadable. */
  jobs_held_by_exports: number;
  cleaning_total: number;
  cleaning_retention_days: number;
  cleaning_due: number;
}

export interface HousekeepingSweepResult {
  jobs_removed: number;
  jobs_held: number;
  cleaning_removed: number;
}

export async function fetchHousekeeping(): Promise<HousekeepingStatus> {
  const { data } = await api.get<HousekeepingStatus>("/admin/housekeeping");
  return data;
}

export async function setHousekeeping(
  body: { jobs_retention_days?: number; cleaning_retention_days?: number }
): Promise<HousekeepingStatus> {
  const { data } = await api.patch<HousekeepingStatus>("/admin/housekeeping", body);
  return data;
}

export async function sweepHousekeeping(): Promise<HousekeepingSweepResult> {
  const { data } = await api.post<HousekeepingSweepResult>("/admin/housekeeping/sweep", {});
  return data;
}

// ---- backups ----

export interface BackupItem {
  kind: "catalog" | "dataset" | "key" | "original" | "batch";
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
  /** 0 = no schedule; nothing is taken automatically */
  interval_hours: number;
  hours_since_last: number | null;
  /** the server decides what overdue means, so every screen agrees */
  stale: boolean;
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

// ---- restoring a backup ----

export interface RestoreDataset {
  dataset_id: string;
  name: string;
  rows_in_backup: number;
  rows_now: number;
}

/** What restoring a backup would do, asked before anyone confirms it. */
export interface RestorePlan {
  found: boolean;
  name: string;
  created_at: string;
  verified: boolean;
  include_originals: boolean;
  total_bytes: number;
  datasets_restored: RestoreDataset[];
  datasets_changed: RestoreDataset[];
  /** here now, absent from the backup: these are the ones somebody has to see */
  datasets_removed: RestoreDataset[];
  users_now: number;
  users_in_backup: number | null;
  ends_sessions: boolean;
  pre_restore_dir: string;
  disk_free_bytes: number;
  /** empty means it can go ahead */
  blockers: string[];
}

export interface RestoreStatus {
  active: boolean;
  stage: string;
  name: string;
  started_at: string;
  finished_at: string;
  ok: boolean | null;
  error: string;
  pre_restore_dir: string;
}

export interface KeptState {
  name: string;
  restored: string;
  at: string;
  bytes: number;
}

export async function fetchRestorePlan(name: string): Promise<RestorePlan> {
  const { data } = await api.get<RestorePlan>(
    `/admin/backups/${encodeURIComponent(name)}/restore-plan`
  );
  return data;
}

export async function startRestore(name: string): Promise<RestoreStatus> {
  const { data } = await api.post<RestoreStatus>(
    `/admin/backups/${encodeURIComponent(name)}/restore`
  );
  return data;
}

/**
 * Where the restore has got to.
 *
 * While the swap is happening every endpoint - this one included - answers 503 with the
 * stage in the body, because the database that would otherwise be asked is the file
 * being replaced. So a refusal here is progress, not an error, and the caller reads the
 * stage out of it.
 */
export async function fetchRestoreStatus(): Promise<RestoreStatus> {
  const { data } = await api.get<RestoreStatus>("/admin/restore/status");
  return data;
}

/** The stage carried by a 503, or null when the failure was something else. */
export function maintenanceStage(err: unknown): string | null {
  const response = (err as { response?: { status?: number; data?: { code?: string; stage?: string } } })
    ?.response;
  if (response?.status !== 503 || response?.data?.code !== "maintenance") return null;
  return response.data.stage ?? "";
}

export async function fetchKeptStates(): Promise<KeptState[]> {
  const { data } = await api.get<KeptState[]>("/admin/restore/kept");
  return data;
}

export async function deleteKeptState(name: string): Promise<void> {
  await api.delete(`/admin/restore/kept/${encodeURIComponent(name)}`);
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

export async function setBackupSchedule(hours: number): Promise<BackupSummary> {
  const { data } = await api.patch<BackupSummary>("/admin/backups/schedule", { hours });
  return data;
}
