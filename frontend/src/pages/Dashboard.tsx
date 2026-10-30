import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import { canManageProjects, type DashboardSummary, type Organization, type Project } from "../api/models";
import { useAuth } from "../auth/AuthContext";
import { useOrg } from "../auth/OrgContext";
import { Field, FormError, useSubmit } from "../components/AuthLayout";
import { FilterBar, FilterCheck, FilterSelect, useDebounced } from "../components/Filters";
import { ProjectForm } from "../components/ProjectForm";
import { ProjectList } from "../components/ProjectList";
import { AppShell } from "../components/AppShell";
import { ZellijField } from "../components/Zellij";
import { STATUS_LABEL, formatMoney } from "../lib/format";

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

  return (
    <AppShell>
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

      {orgs !== null && !org && <CreateOrganization onCreated={add} />}

      {org && <OrgOverview key={org.id} org={org} />}
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

function OrgOverview({ org }: { org: Organization }) {
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
  };

  const clearFilters = () => {
    setSearch("");
    setStatus("");
    setOverBudget(false);
  };

  const totals = summary?.totals.length
    ? summary.totals
    : [{ currency: org.default_currency, budget: "", actual: "", remaining: "" }];
  const empty = projects !== null && projects.length === 0 && !filtering;
  const noMatches = projects !== null && projects.length === 0 && filtering;

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
    </>
  );
}

function Amount({ value, currency, negative = false }: { value: string; currency: string; negative?: boolean }) {
  if (value === "") return <span className="totals__value totals__value--empty">— {currency}</span>;
  return <span className={negative ? "totals__value totals__value--over" : "totals__value"}>{formatMoney(value, currency)}</span>;
}
