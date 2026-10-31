import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import {
  canManageProjects,
  type CurrencyTotals,
  type DashboardSummary,
  type Organization,
  type Project,
} from "../api/models";
import { useAuth } from "../auth/AuthContext";
import { useOrg } from "../auth/OrgContext";
import { Field, FormError, useSubmit } from "../components/AuthLayout";
import { FilterBar, FilterCheck, FilterSelect, useDebounced } from "../components/Filters";
import { Agenda } from "../components/Agenda";
import { ProjectForm } from "../components/ProjectForm";
import { ProjectList } from "../components/ProjectList";
import { AppShell } from "../components/AppShell";
import { ZellijField } from "../components/Zellij";
import { STATUS_LABEL, formatMoney, formatPct } from "../lib/format";

const STATUS_FILTERS = [
  { value: "", label: "All except archived" },
  ...["planned", "active", "on_hold", "completed", "archived"].map((s) => ({ value: s, label: STATUS_LABEL[s] })),
];

const SORT_OPTIONS = [
  { value: "newest", label: "Newest first" },
  { value: "name", label: "Name" },
  { value: "end_date", label: "End date" },
];

function greeting(hour: number) {
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function Dashboard() {
  const { user } = useAuth();
  const { orgs, org, error: loadError, add } = useOrg();
  const hello = `${greeting(new Date().getHours())}, ${user?.first_name ?? ""}`;

  return (
    <AppShell>
      {!org && (
        <header className="main__header">
          <h1>{hello}</h1>
        </header>
      )}

      <FormError message={loadError} />

      {orgs === null && !loadError && <p className="muted">Loading…</p>}

      {orgs !== null && !org && <CreateOrganization onCreated={add} />}

      {org && <OrgOverview key={org.id} org={org} hello={hello} />}
    </AppShell>
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

function OrgOverview({ org, hello }: { org: Organization; hello: string }) {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const canCreate = canManageProjects(org.role);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("newest");
  const [overBudget, setOverBudget] = useState(false);
  const q = useDebounced(search.trim());
  const filtering = q !== "" || status !== "" || overBudget;

  const query = new URLSearchParams({ sort });
  if (q) query.set("q", q);
  if (status) query.set("status", status);
  if (overBudget) query.set("over_budget", "true");
  const queryString = query.toString();

  // Bumped after a new project so the deadline panels refresh too.
  const [refreshKey, setRefreshKey] = useState(0);

  const loadSummary = useCallback(() => {
    api<{ summary: DashboardSummary }>(`/organizations/${org.id}/dashboard`)
      .then((s) => setSummary(s.summary))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load your totals."));
  }, [org.id]);

  const loadProjects = useCallback(() => {
    api<{ projects: Project[] }>(`/organizations/${org.id}/projects?${queryString}`)
      .then((p) => {
        setError(null);
        setProjects(p.projects);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load your projects."));
  }, [org.id, queryString]);

  useEffect(loadSummary, [loadSummary]);
  useEffect(loadProjects, [loadProjects]);

  const load = () => {
    loadSummary();
    loadProjects();
    setRefreshKey((k) => k + 1);
  };

  const clearFilters = () => {
    setSearch("");
    setStatus("");
    setOverBudget(false);
  };

  const totals = summary?.totals ?? [];
  const empty = projects !== null && projects.length === 0 && !filtering;
  const noMatches = projects !== null && projects.length === 0 && filtering;

  return (
    <>
      <FormError message={error} />

      <section className="briefing" aria-label="Overview">
        <ZellijField className="briefing__field" />
        <div className="briefing__inner">
          <div className="briefing__hello">
            <h1>{hello}</h1>
            <p>
              {org.name}
              {summary
                ? `, ${summary.project_count} active ${summary.project_count === 1 ? "project" : "projects"}`
                : ""}
              . Amounts in {org.default_currency}.
            </p>
          </div>

          {summary && totals.length === 0 && (
            <p className="briefing__empty">Budgets you set on projects add up here.</p>
          )}
          {totals.map((t) => (
            <BudgetRibbon key={t.currency} totals={t} />
          ))}

          {summary && (summary.over_budget_project_count > 0 || summary.overdue_task_count > 0) && (
            <ul className="briefing__alerts" aria-label="Needs attention">
              {summary.over_budget_project_count > 0 && (
                <li>
                  <button type="button" onClick={() => setOverBudget(true)}>
                    {summary.over_budget_project_count}{" "}
                    {summary.over_budget_project_count === 1 ? "project is" : "projects are"} over budget
                  </button>
                </li>
              )}
              {summary.overdue_task_count > 0 && (
                <li>
                  {summary.overdue_task_count} overdue {summary.overdue_task_count === 1 ? "task" : "tasks"}, listed in
                  the agenda
                </li>
              )}
            </ul>
          )}
        </div>
      </section>

      <div className="dash-grid">
        <aside className="dash-grid__side" aria-label="Agenda">
          <Agenda orgId={org.id} refreshKey={refreshKey} />
        </aside>

        <section aria-labelledby="projects-heading" className="projects-section dash-grid__main">
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
              onSaved={() => {
                setCreating(false);
                load();
              }}
            />
          )}

          {!empty && (
            <FilterBar label="Filter projects">
              <label className="filter filter--grow">
                <span className="filter__label">Search</span>
                <input
                  type="search"
                  placeholder="Name or description"
                  value={search}
                  maxLength={100}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </label>
              <FilterSelect label="Status" value={status} onChange={setStatus} options={STATUS_FILTERS} />
              <FilterSelect label="Sort by" value={sort} onChange={setSort} options={SORT_OPTIONS} />
              <FilterCheck label="Only over budget" checked={overBudget} onChange={setOverBudget} />
            </FilterBar>
          )}

          {projects === null && !error && <p className="muted">Loading…</p>}

          {noMatches && (
            <p className="muted">
              No projects match these filters.{" "}
              <button type="button" className="link-btn" onClick={clearFilters}>
                Clear filters
              </button>
            </p>
          )}

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
      </div>
    </>
  );
}

/** Spending against budget for one currency, as a single bar: the dashboard's headline figure. */
function BudgetRibbon({ totals: t }: { totals: CurrencyTotals }) {
  const used = t.consumed_pct === null ? 0 : Number(t.consumed_pct);
  const over = t.remaining.startsWith("-");
  return (
    <div className={over ? "ribbon ribbon--over" : "ribbon"}>
      <p className="ribbon__headline">
        <span className="ribbon__spent">{formatMoney(t.actual, t.currency)}</span>
        <span className="ribbon__of">spent of {formatMoney(t.budget, t.currency)} budgeted</span>
      </p>
      <div
        className="ribbon__bar"
        role="progressbar"
        aria-label={`Budget used in ${t.currency}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(Math.min(used, 100))}
      >
        <span className="ribbon__fill" style={{ width: `${Math.min(used, 100)}%` }} />
      </div>
      <dl className="ribbon__figures">
        <div>
          <dt>Used</dt>
          <dd>{formatPct(t.consumed_pct)}</dd>
        </div>
        <div>
          <dt>{over ? "Overspent" : "Left to spend"}</dt>
          <dd className={over ? "ribbon__neg" : "ribbon__pos"}>
            {formatMoney(over ? t.remaining.slice(1) : t.remaining, t.currency)}
          </dd>
        </div>
      </dl>
    </div>
  );
}
