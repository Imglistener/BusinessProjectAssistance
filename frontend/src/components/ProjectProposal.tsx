import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { canManageProjects, type Organization, type Project, type ProjectPlan } from "../api/models";
import { errorMessage } from "../lib/errors";
import { PRIORITY_LABEL, formatDate, formatMoney } from "../lib/format";
import { FormError } from "./AuthLayout";

/**
 * A project drafted by the assistant. Nothing exists until the user clicks "Create project";
 * the server validates the (possibly edited) plan again before creating anything.
 */
export function ProjectProposal({ plan, org }: { plan: ProjectPlan; org: Organization }) {
  const canCreate = canManageProjects(org.role);
  const [name, setName] = useState(plan.name);
  const [budget, setBudget] = useState(plan.budget ?? "");
  const [start, setStart] = useState(plan.start_date ?? "");
  const [end, setEnd] = useState(plan.end_date ?? "");
  const [keepMilestone, setKeepMilestone] = useState(() => plan.milestones.map(() => true));
  const [keepTask, setKeepTask] = useState(() => plan.tasks.map(() => true));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Project | null>(null);
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  if (created) {
    return (
      <div className="proposal proposal--done" role="status">
        <p>
          <strong>{created.name}</strong> was created with {keepMilestone.filter(Boolean).length} milestones and{" "}
          {keepTask.filter(Boolean).length} tasks.
        </p>
        <Link className="btn btn--primary btn--link" to={`/app/projects/${created.id}`}>
          Open the project
        </Link>
      </div>
    );
  }

  const create = async () => {
    setBusy(true);
    setError(null);
    const milestones = plan.milestones.filter((_, i) => keepMilestone[i]);
    const kept = new Set(milestones.map((m) => m.title.toLowerCase()));
    try {
      const r = await api<{ project: Project }>(`/organizations/${org.id}/projects/from-plan`, {
        body: {
          ...plan,
          name: name.trim(),
          budget: budget.trim() ? budget.trim().replace(",", ".") : null,
          start_date: start || null,
          end_date: end || null,
          milestones,
          // A task tied to a milestone the user removed stays, just without the milestone.
          tasks: plan.tasks
            .filter((_, i) => keepTask[i])
            .map((t) => ({ ...t, milestone: t.milestone && kept.has(t.milestone.toLowerCase()) ? t.milestone : null })),
        },
      });
      setCreated(r.project);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const toggle = (setter: typeof setKeepTask, i: number) => setter((prev) => prev.map((v, j) => (j === i ? !v : v)));

  return (
    <section className="proposal" aria-label={`Draft project: ${plan.name}`}>
      <header className="proposal__head">
        <span className="tag">Draft project — not created yet</span>
        <p className="muted">Review and adjust, then create it. Untick anything you don't want.</p>
      </header>
      <FormError message={error} />

      <div className="proposal__fields">
        <label className="filter proposal__name">
          <span className="filter__label">Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={200} />
        </label>
        <label className="filter">
          <span className="filter__label">Budget ({plan.currency})</span>
          <input value={budget} inputMode="decimal" onChange={(e) => setBudget(e.target.value)} placeholder="None" />
        </label>
        <label className="filter">
          <span className="filter__label">Start</span>
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </label>
        <label className="filter">
          <span className="filter__label">End</span>
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </label>
      </div>
      {plan.description && <p className="proposal__description">{plan.description}</p>}

      <div className="proposal__lists">
        {plan.milestones.length > 0 && (
          <div>
            <h4>Milestones</h4>
            <ul>
              {plan.milestones.map((m, i) => (
                <li key={`${m.title}-${i}`}>
                  <label className="check">
                    <input type="checkbox" checked={keepMilestone[i]} onChange={() => toggle(setKeepMilestone, i)} />
                    <span>
                      {m.title}
                      {m.due_date && <span className="muted"> — {formatDate(m.due_date)}</span>}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
        )}
        {plan.tasks.length > 0 && (
          <div>
            <h4>Tasks</h4>
            <ul>
              {plan.tasks.map((t, i) => (
                <li key={`${t.title}-${i}`}>
                  <label className="check">
                    <input type="checkbox" checked={keepTask[i]} onChange={() => toggle(setKeepTask, i)} />
                    <span>
                      {t.title}
                      <span className="muted">
                        {" — "}
                        {PRIORITY_LABEL[t.priority]}
                        {t.due_date ? `, due ${formatDate(t.due_date)}` : ""}
                        {t.milestone ? `, ${t.milestone}` : ""}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="form__actions">
        {canCreate ? (
          <button type="button" className="btn btn--primary" onClick={create} disabled={busy || !name.trim()}>
            {busy ? "Creating…" : "Create project"}
          </button>
        ) : (
          <p className="muted">
            Only owners and project managers can create projects. Share this draft with one of them.
          </p>
        )}
        <button type="button" className="btn btn--quiet" onClick={() => setDismissed(true)}>
          Dismiss
        </button>
      </div>
      {plan.budget && (
        <p className="muted proposal__note">
          Budget drafted from the description: {formatMoney(plan.budget, plan.currency)}. Check it before creating.
        </p>
      )}
    </section>
  );
}
