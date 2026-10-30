import type { ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Wordmark } from "./Zellij";

const SOON = ["Projects", "Expenses"];

/** Sidebar and page frame shared by every signed-in screen. */
export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  // Project pages belong to the dashboard section.
  const onAssistant = pathname.startsWith("/app/assistant");
  const linkClass = (active: boolean) => (active ? "rail__link rail__link--active" : "rail__link");

  return (
    <div className="shell">
      <aside className="rail">
        <Wordmark light />
        <nav aria-label="Main">
          <ul className="rail__nav">
            <li>
              <Link to="/app" className={linkClass(!onAssistant)} aria-current={pathname === "/app" ? "page" : undefined}>
                Dashboard
              </Link>
            </li>
            <li>
              <Link to="/app/assistant" className={linkClass(onAssistant)} aria-current={onAssistant ? "page" : undefined}>
                Assistant
              </Link>
            </li>
            {SOON.map((label) => (
              <li key={label}>
                <span className="rail__link rail__link--soon" aria-disabled="true">
                  {label}
                  <small>Soon</small>
                </span>
              </li>
            ))}
          </ul>
        </nav>
        <div className="rail__user">
          <span className="rail__name">
            {user?.first_name} {user?.last_name}
          </span>
          <button
            type="button"
            className="rail__logout"
            onClick={() => {
              logout();
              navigate("/login", { replace: true });
            }}
          >
            Log out
          </button>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
