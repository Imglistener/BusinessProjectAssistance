import type { ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useOrg } from "../auth/OrgContext";
import { Wordmark } from "./Zellij";

/** Sidebar and page frame shared by every signed-in screen. */
export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { orgs, org, select } = useOrg();
  const { pathname } = useLocation();
  const onAssistant = pathname.startsWith("/app/assistant");
  const onMembers = pathname.startsWith("/app/members");
  const onInventory = pathname.startsWith("/app/inventory");
  // Project pages belong to the dashboard section.
  const onDashboard = !onAssistant && !onMembers && !onInventory;
  const linkClass = (active: boolean) => (active ? "rail__link rail__link--active" : "rail__link");

  return (
    <div className="shell">
      <aside className="rail">
        <Wordmark light />
        {orgs && orgs.length > 1 && org && (
          <div className="rail__org">
            <label htmlFor="org-switch">Organization</label>
            <select
              id="org-switch"
              value={org.id}
              onChange={(e) => {
                select(Number(e.target.value));
                navigate("/app");
              }}
            >
              {orgs.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </div>
        )}
        <nav aria-label="Main">
          <ul className="rail__nav">
            <li>
              <Link
                to="/app"
                className={linkClass(onDashboard)}
                aria-current={pathname === "/app" ? "page" : undefined}
              >
                Dashboard
              </Link>
            </li>
            <li>
              <Link
                to="/app/assistant"
                className={linkClass(onAssistant)}
                aria-current={onAssistant ? "page" : undefined}
              >
                Assistant
              </Link>
            </li>
            <li>
              <Link
                to="/app/inventory"
                className={linkClass(onInventory)}
                aria-current={onInventory ? "page" : undefined}
              >
                Inventory
              </Link>
            </li>
            <li>
              <Link to="/app/members" className={linkClass(onMembers)} aria-current={onMembers ? "page" : undefined}>
                Members
              </Link>
            </li>
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
