import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Wordmark } from "./Zellij";

const SOON = ["Projects", "Expenses", "Assistant"];

/** Sidebar and page frame shared by every signed-in screen. */
export function AppShell({ children, currentPage = false }: { children: ReactNode; currentPage?: boolean }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="shell">
      <aside className="rail">
        <Wordmark light />
        <nav aria-label="Main">
          <ul className="rail__nav">
            <li>
              <Link to="/app" className="rail__link rail__link--active" aria-current={currentPage ? "page" : undefined}>
                Dashboard
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
