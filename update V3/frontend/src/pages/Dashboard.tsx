import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { canManageProjects, type DashboardSummary, type Organization, type Project } from "../api/models";
import { useAuth } from "../auth/AuthContext";
import { Field, FormError, useSubmit } from "../components/AuthLayout";
import { ProjectForm } from "../components/ProjectForm";
import { ProjectList } from "../components/ProjectList";
import { Wordmark, ZellijField } from "../components/Zellij";
import { formatMoney } from "../lib/format";

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

        {org && <OrgOverview org={org} />}
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

function OrgOverview({ org }: { org: Organization }) {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const canCreate = canManageProjects(org.role);

  const load = useCallback(() => {
    setError(null);
    Promise.all([
      api<{ summary: DashboardSummary }>(`/organizations/${org.id}/dashboard`),
      api<{ projects: Project[] }>(`/organizations/${org.id}/projects`),
    ])
      .then(([s, p]) => {
        setSummary(s.summary);
        setProjects(p.projects);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load your projects."));
  }, [org.id]);

  useEffect(load, [load]);

  const totals = summary?.totals.length
    ? summary.totals
    : [{ currency: org.default_currency, budget: "", actual: "", remaining: "" }];
  const empty = projects !== null && projects.length === 0;

  return (
    <>
      <FormError message={error} />

      {totals.map((t) => (
        <section key={t.currency} className="totals" aria-label={`Budget totals in ${t.currency}`}>
          <div>
            <span className="totals__label">Total budget</span>
            <Amount value={t.budget} currency={t.currency} />
          </div>
          <div>
            <span className="totals__label">Spent</span>
            <Amount value={t.actual} currency={t.currency} />
          </div>
          <div>
            <span className="totals__label">Remaining</span>
            <Amount value={t.remaining} currency={t.currency} negative={t.remaining.startsWith("-")} />
          </div>
        </section>
      ))}

      {summary && (summary.over_budget_project_count > 0 || summary.overdue_task_count > 0) && (
        <ul className="attention" aria-label="Needs attention">
          {summary.over_budget_project_count > 0 && (
            <li>
              {summary.over_budget_project_count}{" "}
              {summary.over_budget_project_count === 1 ? "project is" : "projects are"} over budget
            </li>
          )}
          {summary.overdue_task_count > 0 && (
            <li>
              {summary.overdue_task_count} overdue {summary.overdue_task_count === 1 ? "task" : "tasks"}
            </li>
          )}
        </ul>
      )}

      <section aria-labelledby="projects-heading" className="projects-section">
        <div className="section-head">
          <h2 id="projects-heading">Projects</h2>
          {canCreate && !creating && !empty && (
            <button type="button" className="btn btn--primary" onClick={() => setCreating(true)}>
              New project
            </button>
          )}
        </div>

        {creating && (
          <ProjectForm
            org={org}
            onCancel={() => setCreating(false)}
            onCreated={() => {
              setCreating(false);
              load();
            }}
          />
        )}

        {projects === null && !error && <p className="muted">Loading…</p>}

        {projects && projects.length > 0 && <ProjectList projects={projects} />}

        {empty && !creating && (
          <div className="empty">
            <ZellijField className="empty__field" />
            <div className="empty__body">
              <h2>No projects yet</h2>
              <p>
                {canCreate
                  ? "Add a project with a budget and dates. Totals, deadlines and warnings start showing here."
                  : "Ask an organization owner or project manager to add the first project."}
              </p>
              {canCreate && (
                <button type="button" className="btn btn--primary" onClick={() => setCreating(true)}>
                  Create a project
                </button>
              )}
            </div>
          </div>
        )}
      </section>
    </>
  );
}

function Amount({ value, currency, negative = false }: { value: string; currency: string; negative?: boolean }) {
  if (value === "") return <span className="totals__value totals__value--empty">— {currency}</span>;
  return <span className={negative ? "totals__value totals__value--over" : "totals__value"}>{formatMoney(value, currency)}</span>;
}
