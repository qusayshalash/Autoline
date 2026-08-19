import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import LoadingState from "./components/LoadingState";
import RequireAuth from "./components/RequireAuth";
import RequirePermission from "./components/RequirePermission";
import Sidebar from "./components/Sidebar";
import DatasetsPage from "./pages/DatasetsPage";
import LoginPage from "./pages/LoginPage";

/*
 * Everything past the first screen is loaded when it is first opened, not before.
 *
 * The whole application used to arrive as one 1.15 MB script, which every user paid for
 * on every first visit regardless of where they were going. Most of that weight is the
 * charting library and the admin panel - the first is needed by two routes out of a
 * dozen, and the second by administrators only.
 *
 * The login page and the file list stay eagerly imported: they are the two screens that
 * are always reached first, and lazy-loading them would only add a spinner in front of
 * the very thing the user came for.
 */
const AdminLayout = lazy(() => import("./components/admin/AdminLayout"));
const StatsLayout = lazy(() => import("./components/stats/StatsLayout"));
const ActivityPage = lazy(() => import("./pages/admin/ActivityPage"));
const FilesPage = lazy(() => import("./pages/admin/FilesPage"));
const LanguagesPage = lazy(() => import("./pages/admin/LanguagesPage"));
const OverviewPage = lazy(() => import("./pages/admin/OverviewPage"));
const RolesPage = lazy(() => import("./pages/admin/RolesPage"));
const SettingsPage = lazy(() => import("./pages/admin/SettingsPage"));
const AdminUsersPage = lazy(() => import("./pages/admin/UsersPage"));
const CleaningPage = lazy(() => import("./pages/CleaningPage"));
const ExplorerPage = lazy(() => import("./pages/ExplorerPage"));
const ImportWizardPage = lazy(() => import("./pages/ImportWizardPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const StatisticsIndexPage = lazy(() => import("./pages/StatisticsIndexPage"));
const StatisticsPage = lazy(() => import("./pages/StatisticsPage"));

/** The data workspace: its own sidebar and full-height content area. */
function Workspace() {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main">
        <Routes>
          <Route path="/" element={<DatasetsPage />} />
          <Route
            path="/datasets/:datasetId/import"
            element={
              <RequirePermission all={["datasets.upload"]}>
                <ImportWizardPage />
              </RequirePermission>
            }
          />
          <Route
            path="/datasets/:datasetId/clean"
            element={
              <RequirePermission all={["datasets.clean"]}>
                <CleaningPage />
              </RequirePermission>
            }
          />
          <Route path="/datasets/:datasetId/explore" element={<ExplorerPage />} />
          <Route path="/datasets/:datasetId/profile" element={<ProfilePage />} />
          {/* user management now lives in the admin panel */}
          <Route path="/users" element={<Navigate to="/admin/users" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    // One boundary around the whole tree: each lazy route needs a fallback, and a
    // single spinner in the content area reads better than one per route.
    <Suspense fallback={<LoadingState />}>
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      {/* Statistics is its own area too: a dashboard, not a view of the grid. It needs
          no more than read access, which every signed-in role has. */}
      <Route
        path="/statistics"
        element={
          <RequireAuth>
            <RequirePermission all={["datasets.view"]}>
              <StatsLayout />
            </RequirePermission>
          </RequireAuth>
        }
      >
        <Route index element={<StatisticsIndexPage />} />
      </Route>
      <Route
        path="/statistics/:datasetId"
        element={
          <RequireAuth>
            <RequirePermission all={["datasets.view"]}>
              <StatsLayout />
            </RequirePermission>
          </RequireAuth>
        }
      >
        <Route index element={<StatisticsPage />} />
      </Route>

      {/* The admin panel is a separate area with its own shell, deliberately not sharing
          chrome with the data workspace. */}
      <Route
        path="/admin"
        element={
          <RequireAuth>
            <RequirePermission
              any={["system.view", "users.view", "roles.view", "languages.manage", "activity.view"]}
            >
              <AdminLayout />
            </RequirePermission>
          </RequireAuth>
        }
      >
        <Route
          index
          element={
            <RequirePermission all={["system.view"]} redirectTo="/admin/users">
              <OverviewPage />
            </RequirePermission>
          }
        />
        <Route
          path="users"
          element={
            <RequirePermission all={["users.view"]}>
              <AdminUsersPage />
            </RequirePermission>
          }
        />
        <Route
          path="roles"
          element={
            <RequirePermission all={["roles.view"]}>
              <RolesPage />
            </RequirePermission>
          }
        />
        <Route
          path="languages"
          element={
            <RequirePermission all={["languages.manage"]}>
              <LanguagesPage />
            </RequirePermission>
          }
        />
        <Route
          path="files"
          element={
            <RequirePermission all={["datasets.view"]}>
              <FilesPage />
            </RequirePermission>
          }
        />
        <Route
          path="activity"
          element={
            <RequirePermission all={["activity.view"]}>
              <ActivityPage />
            </RequirePermission>
          }
        />
        <Route
          path="settings"
          element={
            <RequirePermission all={["system.view"]}>
              <SettingsPage />
            </RequirePermission>
          }
        />
      </Route>

      <Route
        path="/*"
        element={
          <RequireAuth>
            <Workspace />
          </RequireAuth>
        }
      />
    </Routes>
    </Suspense>
  );
}
