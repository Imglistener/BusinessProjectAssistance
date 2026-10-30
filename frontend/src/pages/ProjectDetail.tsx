import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { Project } from "../api/models";
import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { ExpenseSection } from "../components/ExpenseSection";
import { FormError } from "../components/AuthLayout";
import { TaskSection } from "../components/TaskSection";
import { errorMessage } from "../lib/errors";
import { STATUS_LABEL, formatDateRange, formatMoney, formatPct } from "../lib/format";

export default function ProjectDetail() {
  const { projectId } = useParams();
  const { user } = useAuth();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setProject(null);
    setError(null);
    api<{ project: Project }>(`/projects/${projectId}`)
      .then((r) => setProject(r.project))
      .catch((e) =>
        setError(
          e instanceof ApiError && e.status === 404
            ? "We couldn't find that project."
            : errorMessage(e, "Couldn't load this project."),
        ),
      );
  }, [projectId]);

  // Expense and task changes return fresh project figures; keep my_role from the first load.
  const merge = useCallback((p: Project) => setProject((prev) => (prev ? { ...prev, ...p, my_role: prev.my_role } : p)), []);

  return (
    <AppShell>
      <Link to="/app" className="back">
        All projects
      </Link>

      <FormError message={error} />
      {!project && !error && <p className="muted">Loading…</p>}

      {project && user && (
        <>
          <ProjectHeader project={project} />
          <ExpenseSection project={project} userId={user.id} onProjectChange={merge} />
          <TaskSection project={project} userId={user.id} onProjectChange={merge} />
        </>
      )}
    </AppShell>
  );
}

function ProjectHeader({ project }: { project: Project }) {
  const dates = formatDateRange(project.start_date, project.end_date);
  const used = project.consumed_pct === null ? 0 : Math.min(Number(project.consumed_pct), 100);
  const hasBudget = Number(project.budget) > 0;

  return (
    <>
      <header className="main__header">
        <h1>{project.name}</h1>
        <p className="main__org">
          {STATUS_LABEL[project.status]}
          {dates ? `. ${dates}.` : "."}
          {project.task_completion_pct !== null && ` ${formatPct(project.task_completion_pct)} of tasks done.`}
        </p>
      </header>

      {project.status === "archived" && (
        <p className="notice" role="status">
          This project is archived, so its expenses and tasks are read-only.
        </p>
      )}

      <section className="totals" aria-label="Budget">
        <div>
          <span className="totals__label">Budget</span>
          <span className="totals__value">{formatMoney(project.budget, project.currency)}</span>
        </div>
        <div>
          <span className="totals__label">Spent</span>
          <span className="totals__value">{formatMoney(project.actual, project.currency)}</span>
        </div>
        <div>
          <span className="totals__label">Remaining</span>
          <span className={project.over_budget ? "totals__value totals__value--over" : "totals__value"}>
            {formatMoney(project.remaining, project.currency)}
          </span>
        </div>
      </section>

      {hasBudget && (
        <div className="budget-line">
          <div
            className={project.over_budget ? "bar bar--over" : "bar"}
            role="progressbar"
            aria-label="Budget used"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(used)}
          >
            <div className="bar__fill" style={{ width: `${used}%` }} />
          </div>
          <p className={project.over_budget ? "project__note project__note--over" : "project__note"}>
            {project.over_budget
              ? `Over budget by ${formatMoney(project.variance, project.currency)}`
              : `${formatPct(project.consumed_pct)} of the budget used`}
          </p>
        </div>
      )}
    </>
  );
}
