import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import Assistant from "./pages/Assistant";
import Inventory from "./pages/Inventory";
import Invite from "./pages/Invite";
import Dashboard from "./pages/Dashboard";
import ForgotPassword from "./pages/ForgotPassword";
import Login from "./pages/Login";
import Members from "./pages/Members";
import ProjectDetail from "./pages/ProjectDetail";
import Report from "./pages/Report";
import TripDetail from "./pages/TripDetail";
import ResetPassword from "./pages/ResetPassword";
import Signup from "./pages/Signup";
import Splash from "./pages/Splash";

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="boot" role="status">Loading…</div>;
  // Come back to the same page after logging in again.
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Splash />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/invite/:token" element={<Invite />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password/:token" element={<ResetPassword />} />
      <Route
        path="/app/inventory"
        element={
          <RequireAuth>
            <Inventory />
          </RequireAuth>
        }
      />
      <Route
        path="/app/members"
        element={
          <RequireAuth>
            <Members />
          </RequireAuth>
        }
      />
      <Route
        path="/app"
        element={
          <RequireAuth>
            <Dashboard />
          </RequireAuth>
        }
      />
      <Route
        path="/app/assistant"
        element={
          <RequireAuth>
            <Assistant />
          </RequireAuth>
        }
      />
      <Route
        path="/app/projects/:projectId"
        element={
          <RequireAuth>
            <ProjectDetail />
          </RequireAuth>
        }
      />
      <Route
        path="/app/projects/:projectId/trips/:tripId"
        element={
          <RequireAuth>
            <TripDetail />
          </RequireAuth>
        }
      />
      <Route
        path="/app/projects/:projectId/report"
        element={
          <RequireAuth>
            <Report />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
