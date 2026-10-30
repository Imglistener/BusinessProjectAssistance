import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useOrg } from "../auth/OrgContext";
import { Wordmark } from "./Zellij";

/** Fired after notifications are read, so the sidebar count refreshes at once. */
export const NOTIFICATIONS_CHANGED = "bpa:notifications-changed";
const POLL_MS = 60_000;

function useUnreadCount(): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let alive = true;
    const check = () =>
      api<{ unread_count: number }>("/notifications?limit=1")
        .then((r) => alive && setCount(r.unread_count))
        .catch(() => undefined);
    check();
    const timer = window.setInterval(() => document.visibilityState === "visible" && check(), POLL_MS);
    window.addEventListener(NOTIFICATIONS_CHANGED, check);
    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener(NOTIFICATIONS_CHANGED, check);
    };
  }, []);
  return count;
}

/** Sidebar and page frame shared by every signed-in screen. */
export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { orgs, org, select } = useOrg();
  const { pathname } = useLocation();
  const onAssistant = pathname.startsWith("/app/assistant");
  const onMembers = pathname.startsWith("/app/members");
  const onInventory = pathname.startsWith("/app/inventory");
  const onNotifications = pathname.startsWith("/app/notifications");
  const unread = useUnreadCount();
  // Project pages belong to the dashboard section.
  const onDashboard = !onAssistant && !onMembers && !onInventory && !onNotifications;
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
              <Link
                to="/app/notifications"
                className={linkClass(onNotifications)}
                aria-current={onNotifications ? "page" : undefined}
              >
                Notifications
                {unread > 0 && (
                  <span className="rail__badge" aria-label={`${unread} unread`}>
                    {unread > 99 ? "99+" : unread}
                  </span>
                )}
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
