import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { api } from "../api/client";
import type { AppNotification } from "../api/models";
import { useOrg } from "../auth/OrgContext";
import { AppShell, NOTIFICATIONS_CHANGED } from "../components/AppShell";
import { FormError } from "../components/AuthLayout";
import { formatWhen } from "../lib/activity";
import { errorMessage } from "../lib/errors";
import { t } from "../i18n";

export default function Notifications() {
  const navigate = useNavigate();
  const { orgs, select } = useOrg();
  const [items, setItems] = useState<AppNotification[] | null>(null);
  const [unread, setUnread] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api<{ notifications: AppNotification[]; unread_count: number }>("/notifications?limit=50")
      .then((r) => {
        setItems(r.notifications);
        setUnread(r.unread_count);
      })
      .catch((e) => setError(errorMessage(e, t("Couldn't load notifications."))));
  }, []);

  useEffect(load, [load]);

  const changed = () => window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED));

  const open = async (n: AppNotification) => {
    if (!n.read) {
      await api(`/notifications/${n.id}/read`, { method: "POST" }).catch(() => undefined);
      changed();
    }
    // The link belongs to the notification's organization; switch to it first.
    if (orgs?.some((o) => o.id === n.organization_id)) select(n.organization_id);
    if (n.link) navigate(n.link);
    else load();
  };

  const readAll = async () => {
    try {
      await api("/notifications/read-all", { method: "POST" });
      changed();
      load();
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const multiOrg = (orgs?.length ?? 0) > 1;

  return (
    <AppShell>
      <header className="main__header">
        <div className="header-actions">
          <h1>{t("Notifications")}</h1>
          {unread > 0 && (
            <button type="button" className="link-btn" onClick={readAll}>
              {t("Mark all as read")}
            </button>
          )}
        </div>
        <p className="main__org">{t("Assignments, trips, budget and stock alerts meant for you.")}</p>
      </header>
      <FormError message={error} />
      {items === null && !error && <p className="muted">{t("Loading…")}</p>}
      {items && items.length === 0 && <p className="muted">{t("Nothing yet. You'll see things here when they need you.")}</p>}
      {items && items.length > 0 && (
        <ul className="notes">
          {items.map((n) => (
            <li key={n.id}>
              <button type="button" className={n.read ? "note" : "note note--unread"} onClick={() => open(n)}>
                <span className="note__title">
                  {!n.read && <span className="note__dot" aria-label={t("Unread")} />}
                  {n.title}
                </span>
                {n.body && <span className="note__body">{n.body}</span>}
                <span className="note__meta">
                  {formatWhen(n.created_at)}
                  {multiOrg && n.organization_name ? ` — ${n.organization_name}` : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </AppShell>
  );
}
