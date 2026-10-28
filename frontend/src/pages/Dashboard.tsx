import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Field, FormError, useSubmit } from "../components/AuthLayout";
import { Wordmark, ZellijField } from "../components/Zellij";

interface Organization {
  id: number;
  name: string;
  default_currency: string;
  role: string;
}

const NAV = [
  { label: "Dashboard", active: true },
  { label: "Projects" },
  { label: "Expenses" },
  { label: "Assistant" },
];

function greeting(hour: number) {
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function Dashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [orgs, setOrgs] = useState<Organization[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    api<{ organizations: Organization[] }>("/organizations")
      .then((r) => setOrgs(r.organizations))
      .catch((e) => setLoadError(e instanceof ApiError ? e.message : "Couldn't load your organizations."));
  }, []);

  const org = orgs?.[0] ?? null;

  return (
    <div className="shell">
      <aside className="rail">
        <Wordmark light />
        <nav aria-label="Main">
          <ul className="rail__nav">
            {NAV.map((item) => (
              <li key={item.label}>
                {item.active ? (
                  <a href="/app" className="rail__link rail__link--active" aria-current="page">
                    {item.label}
                  </a>
                ) : (
                  <span className="rail__link rail__link--soon" aria-disabled="true">
                    {item.label}
                    <small>Soon</small>
                  </span>
                )}
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

      <main className="main">
        <header className="main__header">
          <h1>
            {greeting(new Date().getHours())}, {user?.first_name}
          </h1>
          {org && (
            <p className="main__org">
              {org.name}. Amounts in {org.default_currency}.
            </p>
          )}
        </header>

        <FormError message={loadError} />

        {orgs === null && !loadError && <p className="muted">Loading…</p>}

        {orgs !== null && !org && <CreateOrganization onCreated={(o) => setOrgs([o])} />}

        {org && (
          <>
            <section className="totals" aria-label="Budget totals">
              <div>
                <span className="totals__label">Total budget</span>
                <span className="totals__value">— {org.default_currency}</span>
              </div>
              <div>
                <span className="totals__label">Spent</span>
                <span className="totals__value">— {org.default_currency}</span>
              </div>
              <div>
                <span className="totals__label">Remaining</span>
                <span className="totals__value">— {org.default_currency}</span>
              </div>
            </section>

            <section className="empty">
              <ZellijField className="empty__field" />
              <div className="empty__body">
                <h2>No projects yet</h2>
                <p>
                  Totals, deadlines and warnings show up here once your first project has a budget. Project creation
                  is the next thing we're building.
                </p>
                <button type="button" className="btn btn--primary" disabled>
                  Create a project
                </button>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}

function CreateOrganization({ onCreated }: { onCreated(org: Organization): void }) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      const r = await api<{ organization: Organization }>("/organizations", { body: { name: name.trim() } });
      onCreated(r.organization);
    },
    (e) => setError(e instanceof ApiError ? e.message : "Something went wrong. Try again."),
  );

  return (
    <section className="empty empty--form">
      <ZellijField className="empty__field" />
      <div className="empty__body">
        <h2>Name your organization</h2>
        <p>Projects, budgets and teammates live inside an organization. You'll be its owner. Amounts default to MAD.</p>
        <form onSubmit={submit} className="form form--inline">
          <FormError message={error} />
          <Field label="Organization name" name="org_name" value={name} onChange={setName} />
          <button className="btn btn--primary" type="submit" disabled={busy}>
            {busy ? "Creating…" : "Create organization"}
          </button>
        </form>
      </div>
    </section>
  );
}
