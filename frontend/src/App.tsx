import { Navigate, Route, Routes } from "react-router-dom";

import AdminLayout from "./components/admin/AdminLayout";
import RequireAuth from "./components/RequireAuth";
import RequirePermission from "./components/RequirePermission";
import Sidebar from "./components/Sidebar";
import StatsLayout from "./components/stats/StatsLayout";
import ActivityPage from "./pages/admin/ActivityPage";
import FilesPage from "./pages/admin/FilesPage";
import LanguagesPage from "./pages/admin/LanguagesPage";
import OverviewPage from "./pages/admin/OverviewPage";
import RolesPage from "./pages/admin/RolesPage";
import SettingsPage from "./pages/admin/SettingsPage";
import AdminUsersPage from "./pages/admin/UsersPage";
import CleaningPage from "./pages/CleaningPage";
import DatasetsPage from "./pages/DatasetsPage";
import ExplorerPage from "./pages/ExplorerPage";
import ImportWizardPage from "./pages/ImportWizardPage";
import LoginPage from "./pages/LoginPage";
import StatisticsIndexPage from "./pages/StatisticsIndexPage";
import StatisticsPage from "./pages/StatisticsPage";

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
  );
}
