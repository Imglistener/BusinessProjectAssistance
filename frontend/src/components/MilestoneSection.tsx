import { useState } from "react";
import { ApiError, api } from "../api/client";
import { canManageProjects, type Milestone, type Project } from "../api/models";
import { errorMessage } from "../lib/errors";
import { formatDate, formatPct } from "../lib/format";
import { Field, FormError, useSubmit } from "./AuthLayout";

interface Props {
  project: Project;
  milestones: Milestone[] | null;
  /** Reload milestones after a change. */
  onChanged(): void;
}

export function MilestoneSection({ project, milestones, onChanged }: Props) {
  const canManage = project.status !== "archived" && canManageProjects(project.my_role ?? "viewer");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Read-only members see the section only when there's something in it.
  if (!canManage && milestones !== null && milestones.length === 0) return null;

  return (
    <section className="projects-section" aria-labelledby="milestones-heading">
      <div className="section-head">
        <h2 id="milestones-heading">Milestones</h2>
        {canManage && !adding && (
          <button type="button" className="btn btn--primary" onClick={() => setAdding(true)}>
            Add milestone
          </button>
        )}
      </div>

      <FormError message={error} />

      {adding && (
        <MilestoneForm
          project={project}
          onCancel={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            onChanged();
          }}
        />
      )}

      {milestones === null && !error && <p className="muted">Loading…</p>}
      {milestones && milestones.length === 0 && !adding && (
        <p className="muted">No milestones yet. Add key dates, then link tasks to them to track progress.</p>
      )}

      {milestones && milestones.length > 0 && (
        <ul className="rows">
          {milestones.map((m) => (
            <MilestoneRow
              key={m.id}
              project={project}
              milestone={m}
              canManage={canManage}
              onChanged={() => {
                setError(null);
                onChanged();
              }}
              onError={setError}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function MilestoneRow({
  project,
  milestone: m,
  canManage,
  onChanged,
  onError,
}: {
  project: Project;
  milestone: Milestone;
  canManage: boolean;
  onChanged(): void;
  onError(message: string): void;
}) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const done = m.status === "done";
  const pct = m.task_completion_pct === null ? 0 : Number(m.task_completion_pct);

  const run = async (path: string, options: { method: string; body?: unknown }) => {
    setBusy(true);
    try {
      await api(path, options);
      onChanged();
    } catch (e) {
      onError(errorMessage(e));
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  };

  if (editing) {
    return (
      <li className="row row--editing">
        <MilestoneForm
          project={project}
          milestone={m}
          onCancel={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            onChanged();
          }}
        />
      </li>
    );
  }

  return (
    <li className={done ? "row row--voided" : "row"}>
      <div className="row__main milestone">
        <p className="row__title">
          {m.title}
          {done && <span className="tag">Done</span>}
        </p>
        <p className="row__meta">
          {m.due_date ? (
            <span className={m.is_overdue ? "overdue" : undefined}>
              {m.is_overdue ? "Overdue, was due " : "Due "}
              {formatDate(m.due_date)}
            </span>
          ) : (
            "No date"
          )}
          {" — "}
          {m.task_count === 0
            ? "no tasks linked"
            : `${m.done_task_count} of ${m.task_count} tasks done (${formatPct(m.task_completion_pct)})`}
        </p>
        {m.task_count > 0 && (
          <div
            className="bar milestone__bar"
            role="progressbar"
            aria-label={`Tasks done for ${m.title}`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(pct)}
          >
            <div className="bar__fill" style={{ width: `${pct}%` }} />
          </div>
        )}
      </div>
      {canManage && (
        <div className="row__side">
          {confirming ? (
            <span className="row__confirm">
              <button
                type="button"
                className="link-btn link-btn--danger"
                disabled={busy}
                onClick={() => run(`/milestones/${m.id}`, { method: "DELETE" })}
              >
                {busy ? "Deleting…" : "Delete milestone"}
              </button>
              <button type="button" className="link-btn" onClick={() => setConfirming(false)} disabled={busy}>
                Keep
              </button>
            </span>
          ) : (
            <span className="row__confirm">
              <button
                type="button"
                className="link-btn"
                disabled={busy}
                onClick={() =>
                  run(`/milestones/${m.id}`, { method: "PATCH", body: { status: done ? "open" : "done" } })
                }
              >
                {done ? "Reopen" : "Mark done"}
              </button>
              <button type="button" className="link-btn" onClick={() => setEditing(true)}>
                Edit
              </button>
              <button
                type="button"
                className="link-btn"
                onClick={() => setConfirming(true)}
                title="Its tasks stay in the project, without a milestone."
              >
                Delete
              </button>
            </span>
          )}
        </div>
      )}
    </li>
  );
}

function MilestoneForm({
  project,
  milestone,
  onSaved,
  onCancel,
}: {
  project: Project;
  milestone?: Milestone;
  onSaved(): void;
  onCancel(): void;
}) {
  const [title, setTitle] = useState(milestone?.title ?? "");
  const [due, setDue] = useState(milestone?.due_date ?? "");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const id = milestone ? `milestone_${milestone.id}_` : "milestone_";

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      setFieldErrors({});
      const body = { title: title.trim(), due_date: due || null };
      if (milestone) await api(`/milestones/${milestone.id}`, { method: "PATCH", body });
      else await api(`/projects/${project.id}/milestones`, { body });
      onSaved();
    },
    (e) => {
      if (e instanceof ApiError && e.field) setFieldErrors({ [e.field]: e.message });
      else setError(errorMessage(e));
    },
  );

  return (
    <form onSubmit={submit} className="panel form" aria-label={milestone ? "Edit milestone" : "Add milestone"}>
      <h3 className="panel__title">{milestone ? "Edit milestone" : "Add milestone"}</h3>
      <FormError message={error} />
      <div className="form__row">
        <Field label="Title" name={`${id}title`} value={title} onChange={setTitle} error={fieldErrors.title} />
        <Field
          label="Due date"
          name={`${id}due`}
          type="date"
          value={due}
          onChange={setDue}
          error={fieldErrors.due_date}
          required={false}
        />
      </div>
      <div className="form__actions">
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? "Saving…" : milestone ? "Save changes" : "Save milestone"}
        </button>
        <button className="btn btn--quiet" type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
