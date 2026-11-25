import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "../components/Layout";
import { Loading } from "../components/ui";
import AgentPage from "../features/agent/AgentPage";
import { useAuth } from "../features/auth/AuthProvider";
import LoginPage from "../features/auth/LoginPage";
import PackageDetailPage from "../features/packages/PackageDetailPage";
import PackagesPage from "../features/packages/PackagesPage";
import SettingsPage from "../features/settings/SettingsPage";
import TeamPage from "../features/team/TeamPage";

// Carga diferida: gráficas y escáner pesan más y no se necesitan al iniciar sesión.
const DashboardPage = lazy(() => import("../features/dashboard/DashboardPage"));
const ScannerPage = lazy(() => import("../features/scanner/ScannerPage"));

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <LoginPage />;
  const owner = user.role === "owner";
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="packages" element={<PackagesPage />} />
          <Route path="packages/:id" element={<PackageDetailPage />} />
          <Route path="scanner" element={<ScannerPage />} />
          <Route path="agent" element={<AgentPage />} />
          {owner && <Route path="team" element={<TeamPage />} />}
          {owner && <Route path="settings" element={<SettingsPage />} />}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
