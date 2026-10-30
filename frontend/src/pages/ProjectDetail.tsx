import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { canManageProjects, type Milestone, type Project } from "../api/models";
import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { ExpenseSection } from "../components/ExpenseSection";
import { FormError } from "../components/AuthLayout";
import { MilestoneSection } from "../components/MilestoneSection";
import { ProjectForm } from "../components/ProjectForm";
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
  const merge = useCallback(
    (p: Project) => setProject((prev) => (prev ? { ...prev, ...p, my_role: prev.my_role } : p)),
    [],
  );

  const [milestones, setMilestones] = useState<Milestone[] | null>(null);
  const loadMilestones = useCallback(() => {
    api<{ milestones: Milestone[] }>(`/projects/${projectId}/milestones`)
      .then((r) => setMilestones(r.milestones))
      .catch(() => setMilestones([]));
  }, [projectId]);

  useEffect(() => {
    setMilestones(null);
    loadMilestones();
  }, [loadMilestones]);

  // Task changes move milestone progress too.
  const onTaskChange = useCallback(
    (p: Project) => {
      merge(p);
      loadMilestones();
    },
    [merge, loadMilestones],
  );

  return (
    <AppShell>
      <Link to="/app" className="back">
        All projects
      </Link>

      <FormError message={error} />
      {!project && !error && <p className="muted">Loading…</p>}

      {project && user && (
        <>
          <ProjectHeader project={project} onProjectChange={merge} />
          <MilestoneSection project={project} milestones={milestones} onChanged={loadMilestones} />
          <TaskSection
            project={project}
            userId={user.id}
            milestones={milestones ?? []}
            onProjectChange={onTaskChange}
          />
          <ExpenseSection project={project} userId={user.id} onProjectChange={merge} />
        </>
      )}
    </AppShell>
  );
}

function ProjectActions({ project, onProjectChange }: { project: Project; onProjectChange(p: Project): void }) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const archived = project.status === "archived";

  const run = async (path: string, options: { method: string; body?: unknown }) => {
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ project: Project }>(path, options);
      onProjectChange(r.project);
      setConfirming(false);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  if (editing) {
    return (
      <ProjectForm
        project={project}
        onCancel={() => setEditing(false)}
        onSaved={(p) => {
          onProjectChange(p);
          setEditing(false);
        }}
      />
    );
  }

  return (
    <div className="project-actions">
      <FormError message={error} />
      {archived ? (
        <button
          type="button"
          className="btn btn--primary"
          disabled={busy}
          onClick={() => run(`/projects/${project.id}`, { method: "PATCH", body: { status: "active" } })}
        >
          {busy ? "Restoring…" : "Restore project"}
        </button>
      ) : (
        <>
          <button type="button" className="btn btn--secondary" onClick={() => setEditing(true)}>
            Edit project
          </button>
          {confirming ? (
            <span className="row__confirm">
              <span>Archive it? Its expenses and tasks become read-only.</span>
              <button
                type="button"
                className="link-btn link-btn--danger"
                disabled={busy}
                onClick={() => run(`/projects/${project.id}/archive`, { method: "POST" })}
              >
                {busy ? "Archiving…" : "Archive"}
              </button>
              <button type="button" className="link-btn" onClick={() => setConfirming(false)} disabled={busy}>
                Keep
              </button>
            </span>
          ) : (
            <button type="button" className="link-btn" onClick={() => setConfirming(true)}>
              Archive
            </button>
          )}
        </>
      )}
    </div>
  );
}

function ProjectHeader({ project, onProjectChange }: { project: Project; onProjectChange(p: Project): void }) {
  const canManage = project.my_role !== undefined && canManageProjects(project.my_role);
  const dates = formatDateRange(project.start_date, project.end_date);
  const used = project.consumed_pct === null ? 0 : Math.min(Number(project.consumed_pct), 100);
  const hasBudget = Number(project.budget) > 0;

  return (
    <>
      <header className="main__header">
        <div className="header-actions">
          <h1>{project.name}</h1>
          <span className="header-links">
            <Link to={`/app/projects/${project.id}/report`}>Report</Link>
            <Link to={`/app/assistant?project=${project.id}`}>Ask the assistant</Link>
          </span>
        </div>
        <p className="main__org">
          {STATUS_LABEL[project.status]}
          {dates ? `. ${dates}.` : "."}
          {project.task_completion_pct !== null && ` ${formatPct(project.task_completion_pct)} of tasks done.`}
        </p>
        {project.description && <p className="project__description">{project.description}</p>}
      </header>

      {project.status === "archived" && (
        <p className="notice" role="status">
          This project is archived, so its expenses and tasks are read-only.
          {canManage ? " Restore it to make changes." : ""}
        </p>
      )}

      {canManage && <ProjectActions project={project} onProjectChange={onProjectChange} />}

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
