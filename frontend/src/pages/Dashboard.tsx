import { AlertTriangle, CheckSquare, CircleDollarSign, Clock, FolderPlus, Plus, Search, Trash2, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
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
import { useSubmit } from "../components/AuthLayout";
import { useDebounced } from "../components/Filters";
import { Agenda } from "../components/Agenda";
import { AnimatedMoney } from "../components/AnimatedMoney";
import { FormAlert, SimpleSelect, TextField } from "../components/form";
import { LogoMark } from "../components/Logo";
import { DeleteProjectsDialog } from "../components/DeleteProjectsDialog";
import { ProjectFormDialog } from "../components/ProjectForm";
import { ProjectList } from "../components/ProjectList";
import { AppShell } from "../components/AppShell";
import { STATUS_LABEL, formatMoney, formatPct } from "../lib/format";
import { t } from "../i18n";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const STATUS_FILTERS = [
  { value: "", label: t("All except archived") },
  ...["planned", "active", "on_hold", "completed", "archived"].map((s) => ({ value: s, label: STATUS_LABEL[s] })),
];

const SORT_OPTIONS = [
  { value: "newest", label: t("Newest first") },
  { value: "name", label: t("Name") },
  { value: "end_date", label: t("End date") },
];

function greeting(hour: number) {
  if (hour < 12) return t("Good morning");
  if (hour < 18) return t("Good afternoon");
  return t("Good evening");
}

/** Cards rise in one short, staggered sequence on load; nothing moves after that. */
const rise = (i: number) => ({
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.3, delay: i * 0.05, ease: [0.2, 0.7, 0.2, 1] as const },
});

export default function Dashboard() {
  const { user } = useAuth();
  const { orgs, org, error: loadError, add } = useOrg();
  const hello = t("{greeting}, {name}", { greeting: greeting(new Date().getHours()), name: user?.first_name ?? "" });

  return (
    <AppShell legacy={false}>
      <div className="mx-auto grid w-full max-w-7xl gap-6 p-4 md:p-8">
        <FormAlert message={loadError} />
        {orgs === null && !loadError && <DashboardSkeleton />}
        {orgs !== null && !org && <CreateOrganization hello={hello} onCreated={add} />}
        {org && <OrgOverview key={org.id} org={org} hello={hello} />}
      </div>
    </AppShell>
  );
}

function DashboardSkeleton() {
  return (
    <div className="grid gap-6" role="status" aria-label={t("Loading…")}>
      <Skeleton className="h-9 w-72" />
      <div className="grid gap-4 md:grid-cols-3">
        <Skeleton className="h-40 md:col-span-2" />
        <Skeleton className="h-40" />
      </div>
      <Skeleton className="h-96" />
    </div>
  );
}

function CreateOrganization({ hello, onCreated }: { hello: string; onCreated(org: Organization): void }) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      const r = await api<{ organization: Organization }>("/organizations", { body: { name: name.trim() } });
      onCreated(r.organization);
    },
    (e) => setError(e instanceof ApiError ? e.message : t("Something went wrong. Try again.")),
  );

  return (
    <motion.div {...rise(0)} className="mx-auto grid w-full max-w-lg gap-6 pt-10">
      <h1 className="text-2xl font-semibold tracking-tight">{hello}</h1>
      <Card>
        <CardHeader>
          <span className="mb-2 flex size-10 items-center justify-center rounded-xl bg-primary/10">
            <LogoMark className="size-6 text-primary" />
          </span>
          <CardTitle>{t("Name your organization")}</CardTitle>
          <CardDescription>
            {t("Projects, budgets and teammates live inside an organization. You'll be its owner. Amounts default to MAD.")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="grid gap-4">
            <FormAlert message={error} />
            <TextField
              id="org_name"
              label={t("Organization name")}
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={200}
              autoFocus
            />
            <Button type="submit" disabled={busy} className="justify-self-start">
              {busy ? t("Creating…") : t("Create organization")}
            </Button>
          </form>
        </CardContent>
      </Card>
    </motion.div>
  );
}

function OrgOverview({ org, hello }: { org: Organization; hello: string }) {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const canCreate = canManageProjects(org.role);
  // Deleting is for owners; they pick projects with "Select", then delete them together.
  const canDelete = org.role === "owner";
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const [deletedCount, setDeletedCount] = useState<number | null>(null);
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

  // Bumped after a new project so the agenda refreshes too.
  const [refreshKey, setRefreshKey] = useState(0);

  const loadSummary = useCallback(() => {
    api<{ summary: DashboardSummary }>(`/organizations/${org.id}/dashboard`)
      .then((s) => setSummary(s.summary))
      .catch((e) => setError(e instanceof ApiError ? e.message : t("Couldn't load your totals.")));
  }, [org.id]);

  const loadProjects = useCallback(() => {
    api<{ projects: Project[] }>(`/organizations/${org.id}/projects?${queryString}`)
      .then((p) => {
        setError(null);
        setProjects(p.projects);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : t("Couldn't load your projects.")));
  }, [org.id, queryString]);

  useEffect(loadSummary, [loadSummary]);
  useEffect(loadProjects, [loadProjects]);

  const reload = () => {
    loadSummary();
    loadProjects();
    setRefreshKey((k) => k + 1);
  };

  // Only projects still on screen stay selected when the filters change.
  useEffect(() => {
    if (!projects) return;
    const visible = new Set(projects.map((p) => p.id));
    setSelected((s) => new Set([...s].filter((id) => visible.has(id))));
  }, [projects]);

  const toggle = (id: number) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const allSelected = !!projects && projects.length > 0 && projects.every((p) => selected.has(p.id));
  const stopSelecting = () => {
    setSelecting(false);
    setSelected(new Set());
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
      <motion.header {...rise(0)} className="flex flex-wrap items-end justify-between gap-4">
        <div className="grid gap-1">
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">{hello}</h1>
          <p className="text-sm text-muted-foreground">
            {org.name}
            {summary ? `${t(", ")}${t("{count} active projects", { count: summary.project_count })}` : ""}.{" "}
            {t("Amounts in {currency}.", { currency: org.default_currency })}
          </p>
        </div>
        {canCreate && (
          <Button onClick={() => setCreating(true)}>
            <Plus className="size-4" />
            {t("New project")}
          </Button>
        )}
      </motion.header>

      <FormAlert message={error} />

      <section aria-label={t("Overview")} className="grid gap-4 md:grid-cols-3">
        {summary === null ? (
          <>
            <Skeleton className="h-44 md:col-span-2" />
            <Skeleton className="h-44" />
          </>
        ) : (
          <>
            <motion.div {...rise(1)} className="grid gap-4 md:col-span-2">
              {totals.length === 0 ? (
                <Card className="h-full justify-center">
                  <CardContent className="flex items-center gap-3 text-sm text-muted-foreground">
                    <CircleDollarSign className="size-5" />
                    {t("Budgets you set on projects add up here.")}
                  </CardContent>
                </Card>
              ) : (
                totals.map((c) => <BudgetCard key={c.currency} totals={c} />)
              )}
            </motion.div>
            <motion.div {...rise(2)} className="grid gap-4">
              <AttentionCard
                icon={<AlertTriangle className="size-4" />}
                tone={summary.over_budget_project_count > 0 ? "danger" : "calm"}
                value={summary.over_budget_project_count}
                label={t("Projects over budget")}
                onClick={summary.over_budget_project_count > 0 ? () => setOverBudget(true) : undefined}
              />
              <AttentionCard
                icon={<Clock className="size-4" />}
                tone={summary.overdue_task_count > 0 ? "warning" : "calm"}
                value={summary.overdue_task_count}
                label={t("Overdue tasks")}
              />
            </motion.div>
          </>
        )}
      </section>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <motion.section {...rise(3)} aria-labelledby="projects-heading">
          <Card className="gap-0 py-0">
            <CardHeader className="gap-4 border-b py-5">
              <div className="flex items-center justify-between gap-2">
                <CardTitle id="projects-heading" className="flex items-center gap-3 text-base">
                  {selecting && projects && projects.length > 0 && (
                    <Checkbox
                      checked={allSelected ? true : selected.size > 0 ? "indeterminate" : false}
                      onCheckedChange={() => setSelected(allSelected ? new Set() : new Set(projects.map((p) => p.id)))}
                      aria-label={t("Select all")}
                    />
                  )}
                  <span>
                    {t("Projects")}
                    {projects && projects.length > 0 && (
                      <span className="tabular ms-2 text-sm font-normal text-muted-foreground">{projects.length}</span>
                    )}
                  </span>
                </CardTitle>
                {canDelete && !empty && (
                  <Button
                    variant={selecting ? "secondary" : "ghost"}
                    size="sm"
                    onClick={() => (selecting ? stopSelecting() : setSelecting(true))}
                  >
                    {selecting ? <X className="size-4" /> : <CheckSquare className="size-4" />}
                    {selecting ? t("Done") : t("Select")}
                  </Button>
                )}
              </div>
              <AnimatePresence>
                {deletedCount !== null && (
                  <motion.p
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    role="status"
                    className="text-sm text-emerald-700 dark:text-emerald-400"
                  >
                    {t("{count} projects deleted.", { count: deletedCount })}
                  </motion.p>
                )}
              </AnimatePresence>
              {!empty && (
                <div role="search" aria-label={t("Filter projects")} className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_11rem_10rem]">
                  <div className="relative">
                    <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      type="search"
                      placeholder={t("Name or description")}
                      aria-label={t("Search")}
                      value={search}
                      maxLength={100}
                      onChange={(e) => setSearch(e.target.value)}
                      className="ps-9"
                    />
                  </div>
                  <SimpleSelect ariaLabel={t("Status")} value={status} onChange={setStatus} options={STATUS_FILTERS} />
                  <SimpleSelect ariaLabel={t("Sort by")} value={sort} onChange={setSort} options={SORT_OPTIONS} />
                  <div className="flex items-center gap-2 sm:col-span-3">
                    <Checkbox id="over-budget" checked={overBudget} onCheckedChange={(v) => setOverBudget(v === true)} />
                    <Label htmlFor="over-budget" className="text-sm font-normal text-muted-foreground">
                      {t("Only over budget")}
                    </Label>
                    {filtering && (
                      <Button variant="ghost" size="sm" className="ms-auto h-7 text-xs" onClick={clearFilters}>
                        <X className="size-3.5" />
                        {t("Clear filters")}
                      </Button>
                    )}
                  </div>
                </div>
              )}
            </CardHeader>
            <CardContent className="px-2 py-1">
              {projects === null && !error && (
                <div className="grid gap-4 p-4">
                  {[0, 1, 2].map((i) => (
                    <Skeleton key={i} className="h-16" />
                  ))}
                </div>
              )}
              {noMatches && (
                <p className="px-4 py-10 text-center text-sm text-muted-foreground">{t("No projects match these filters.")}</p>
              )}
              {projects && projects.length > 0 && (
                <ProjectList projects={projects} selection={selecting ? { selected, toggle } : undefined} />
              )}
              {empty && (
                <div className="grid justify-items-center gap-3 px-6 py-14 text-center">
                  <span className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                    <FolderPlus className="size-6" />
                  </span>
                  <h2 className="font-semibold">{t("No projects yet")}</h2>
                  <p className="max-w-sm text-sm text-muted-foreground">
                    {canCreate
                      ? t("Add a project with a budget and dates. Totals, deadlines and warnings start showing here.")
                      : t("Ask an organization owner or project manager to add the first project.")}
                  </p>
                  {canCreate && (
                    <Button onClick={() => setCreating(true)} className="mt-2">
                      <Plus className="size-4" />
                      {t("Create a project")}
                    </Button>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </motion.section>

        <motion.aside {...rise(4)} aria-label={t("Agenda")} className="lg:sticky lg:top-20">
          <Agenda orgId={org.id} refreshKey={refreshKey} />
        </motion.aside>
      </div>

      <AnimatePresence>
        {selecting && selected.size > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 16 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-x-0 bottom-6 z-30 flex justify-center px-4"
          >
            <div className="flex items-center gap-3 rounded-full border bg-popover py-2 ps-5 pe-2 text-sm shadow-lg">
              <span className="tabular font-medium">{t("{count} selected", { count: selected.size })}</span>
              <Button variant="ghost" size="sm" className="rounded-full" onClick={() => setSelected(new Set())}>
                {t("Clear")}
              </Button>
              <Button variant="destructive" size="sm" className="rounded-full" onClick={() => setDeleting(true)}>
                <Trash2 className="size-4" />
                {t("Delete")}
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <DeleteProjectsDialog
        orgId={org.id}
        projectIds={[...selected]}
        open={deleting}
        onOpenChange={setDeleting}
        onDeleted={(count) => {
          stopSelecting();
          setDeletedCount(count);
          window.setTimeout(() => setDeletedCount(null), 5000);
          reload();
        }}
      />

      <ProjectFormDialog
        open={creating}
        onOpenChange={setCreating}
        org={org}
        onSaved={() => {
          setCreating(false);
          reload();
        }}
      />
    </>
  );
}

/** Spending against budget for one currency: the dashboard's headline figure. */
function BudgetCard({ totals: c }: { totals: CurrencyTotals }) {
  const used = c.consumed_pct === null ? 0 : Number(c.consumed_pct);
  const over = c.remaining.startsWith("-");
  return (
    <Card className="relative h-full overflow-hidden">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -end-24 -top-24 size-64 rounded-full bg-primary/10 blur-3xl"
      />
      <CardHeader>
        <CardDescription>{t("Budget used in {currency}", { currency: c.currency })}</CardDescription>
        <CardTitle className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <AnimatedMoney amount={c.actual} currency={c.currency} className="tabular text-3xl font-semibold tracking-tight md:text-4xl" />
          <span className="tabular text-sm font-normal text-muted-foreground">
            {t("spent of {amount} budgeted", { amount: formatMoney(c.budget, c.currency) })}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div
          className="h-2.5 overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-label={t("Budget used in {currency}", { currency: c.currency })}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(Math.min(used, 100))}
        >
          <motion.div
            className={cn("h-full rounded-full", over ? "bg-destructive" : "bg-primary")}
            initial={{ width: 0 }}
            animate={{ width: `${Math.min(used, 100)}%` }}
            transition={{ duration: 0.9, delay: 0.15, ease: [0.2, 0.7, 0.2, 1] }}
          />
        </div>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Stat label={t("Used")} value={formatPct(c.consumed_pct)} />
          <Stat
            label={over ? t("Overspent") : t("Left to spend")}
            value={formatMoney(over ? c.remaining.slice(1) : c.remaining, c.currency)}
            tone={over ? "danger" : "good"}
          />
          <Stat label={t("Budget")} value={formatMoney(c.budget, c.currency)} className="hidden sm:grid" />
        </dl>
      </CardContent>
    </Card>
  );
}

function Stat({ label, value, tone, className }: { label: string; value: string; tone?: "good" | "danger"; className?: string }) {
  return (
    <div className={cn("grid gap-0.5", className)}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd
        className={cn(
          "tabular text-base font-semibold",
          tone === "good" && "text-emerald-600 dark:text-emerald-400",
          tone === "danger" && "text-destructive",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

function AttentionCard({
  icon,
  value,
  label,
  tone,
  onClick,
}: {
  icon: ReactNode;
  value: number;
  label: string;
  tone: "danger" | "warning" | "calm";
  onClick?: () => void;
}) {
  const body = (
    <CardContent className="flex items-center gap-4">
      <span
        className={cn(
          "flex size-10 shrink-0 items-center justify-center rounded-xl",
          tone === "danger" && "bg-destructive/10 text-destructive",
          tone === "warning" && "bg-warning/15 text-amber-600 dark:text-amber-300",
          tone === "calm" && "bg-muted text-muted-foreground",
        )}
      >
        {icon}
      </span>
      <span className="grid min-w-0 gap-0.5 text-start">
        <span className="tabular text-2xl font-semibold leading-none">{value}</span>
        <span className="text-sm text-muted-foreground">{label}</span>
      </span>
    </CardContent>
  );
  return onClick ? (
    <Card className="justify-center p-0 transition-shadow hover:shadow-md">
      <button type="button" onClick={onClick} className="w-full rounded-xl py-6 text-start outline-none focus-visible:ring-2 focus-visible:ring-ring">
        {body}
      </button>
    </Card>
  ) : (
    <Card className="justify-center">{body}</Card>
  );
}
