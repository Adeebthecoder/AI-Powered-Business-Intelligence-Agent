// App.jsx
// The list of pages (routes). Every page except Login needs a logged-in user.

import { Navigate, Route, Routes } from "react-router-dom";
import { useApp } from "./AppContext.jsx";
import Layout from "./components/Layout.jsx";
import { Loading } from "./components/States.jsx";
import AdminPage from "./pages/AdminPage.jsx";
import AskPage from "./pages/AskPage.jsx";
import DatasetsPage from "./pages/DatasetsPage.jsx";
import ForecastPage from "./pages/ForecastPage.jsx";
import HistoryPage from "./pages/HistoryPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import OverviewPage from "./pages/OverviewPage.jsx";
import ReportsPage from "./pages/ReportsPage.jsx";

export default function App() {
  const { user, checkingLogin } = useApp();

  if (checkingLogin) {
    return (
      <div className="full-center">
        <Loading text="Loading the app..." />
      </div>
    );
  }

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <Layout>
      <Routes>
        <Route path="/datasets" element={<DatasetsPage />} />
        <Route path="/datasets/:id" element={<OverviewPage />} />
        <Route path="/ask" element={<AskPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/forecast" element={<ForecastPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        {user.role === "admin" && <Route path="/admin" element={<AdminPage />} />}
        <Route path="*" element={<Navigate to="/datasets" replace />} />
      </Routes>
    </Layout>
  );
}
