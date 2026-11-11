import { AlertTriangle, CalendarDays, ChevronRight } from "lucide-react";
import { motion } from "motion/react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import type { Project } from "../api/models";
import { STATUS_LABEL, formatDateRange, formatMoney, formatPct } from "../lib/format";
import { isRtl, t } from "../i18n";
import { tx } from "../i18n/rich";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

/** Over budget beats overdue work; everything else is on track. */
function health(p: Project): "over" | "late" | "ok" {
  if (p.over_budget) return "over";
  if (p.overdue_task_count > 0) return "late";
  return "ok";
}

const STATUS_STYLE: Record<string, string> = {
  planned: "bg-secondary text-secondary-foreground",
  active: "bg-primary/10 text-primary",
  on_hold: "bg-warning/15 text-amber-700 dark:text-amber-300",
  completed: "bg-success/15 text-emerald-700 dark:text-emerald-300",
  archived: "bg-muted text-muted-foreground",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="secondary" className={cn("rounded-md border-0 font-medium", STATUS_STYLE[status])}>
      {STATUS_LABEL[status]}
    </Badge>
  );
}

function BudgetBar({ project }: { project: Project }) {
  const hasBudget = Number(project.budget) > 0;
  if (!hasBudget && Number(project.actual) === 0) {
    return <p className="text-sm text-muted-foreground">{t("No budget set")}</p>;
  }
  const used = project.consumed_pct === null ? 0 : Math.min(Number(project.consumed_pct), 100);
  return (
    <div className="grid gap-1.5">
      <p className="tabular text-sm text-muted-foreground">
        {tx("{spent} spent of {budget}", {
          spent: <span className="font-medium text-foreground">{formatMoney(project.actual, project.currency)}</span>,
          budget: formatMoney(project.budget, project.currency),
        })}
      </p>
      <div
        className="h-1.5 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-label={t("Budget used")}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(used)}
      >
        <motion.div
          className={cn("h-full rounded-full", project.over_budget ? "bg-destructive" : "bg-primary")}
          initial={{ width: 0 }}
          animate={{ width: `${used}%` }}
          transition={{ duration: 0.6, ease: [0.2, 0.7, 0.2, 1] }}
        />
      </div>
      <p className={cn("tabular text-xs", project.over_budget ? "font-medium text-destructive" : "text-muted-foreground")}>
        {project.over_budget
          ? t("Over budget by {amount}", { amount: formatMoney(project.variance, project.currency) })
          : hasBudget
            ? t("{pct} used, {amount} left", {
                pct: formatPct(project.consumed_pct),
                amount: formatMoney(project.remaining, project.currency),
              })
            : null}
      </p>
    </div>
  );
}

/** While selecting, rows toggle a checkbox instead of opening the project. */
export interface ProjectSelection {
  selected: Set<number>;
  toggle(id: number): void;
}

export function ProjectList({ projects, selection }: { projects: Project[]; selection?: ProjectSelection }) {
  return (
    <ul className="divide-y">
      {projects.map((p, i) => {
        const dates = formatDateRange(p.start_date, p.end_date);
        const state = health(p);
        return (
          <motion.li
            key={p.id}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, delay: Math.min(i, 8) * 0.03 }}
          >
            <RowFrame project={p} selection={selection}>
              <span
                aria-hidden="true"
                className={cn(
                  "absolute inset-y-4 start-0 w-1 rounded-full",
                  state === "over" ? "bg-destructive" : state === "late" ? "bg-warning" : "bg-border",
                )}
              />
              <div className="grid min-w-0 gap-1.5">
                <h3 className="project-name truncate font-medium text-foreground">{p.name}</h3>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <StatusBadge status={p.status} />
                  {dates && (
                    <span className="inline-flex items-center gap-1">
                      <CalendarDays className="size-3.5" />
                      {dates}
                    </span>
                  )}
                  {p.overdue_task_count > 0 && (
                    <span className="inline-flex items-center gap-1 font-medium text-destructive">
                      <AlertTriangle className="size-3.5" />
                      {t("{count} overdue tasks", { count: p.overdue_task_count })}
                    </span>
                  )}
                </div>
              </div>
              <BudgetBar project={p} />
              {!selection && (
                <ChevronRight
                  className={cn(
                    "hidden size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 sm:block",
                    isRtl() && "rotate-180 group-hover:-translate-x-0.5",
                  )}
                />
              )}
            </RowFrame>
          </motion.li>
        );
      })}
    </ul>
  );
}

const ROW =
  "group relative grid gap-4 py-4 ps-4 pe-2 transition-colors hover:bg-muted/50 sm:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)_auto] sm:items-center";

/** A link to the project, or, while selecting, a checkbox row. */
function RowFrame({
  project,
  selection,
  children,
}: {
  project: Project;
  selection?: ProjectSelection;
  children: ReactNode;
}) {
  if (!selection) {
    return (
      <Link to={`/app/projects/${project.id}`} className={ROW}>
        {children}
      </Link>
    );
  }
  const checked = selection.selected.has(project.id);
  return (
    <label
      className={cn(
        ROW,
        "cursor-pointer ps-12 sm:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]",
        checked && "bg-primary/5 hover:bg-primary/10",
      )}
    >
      <Checkbox
        checked={checked}
        onCheckedChange={() => selection.toggle(project.id)}
        aria-label={t("Select {name}", { name: project.name })}
        className="absolute start-5 top-1/2 -translate-y-1/2 rtl:translate-y-[-50%]"
      />
      {children}
    </label>
  );
}
