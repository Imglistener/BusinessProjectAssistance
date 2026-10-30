import { useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import {
  canContribute,
  canManageProjects,
  type Project,
  type Task,
  type TaskPriority,
  type TaskStatus,
} from "../api/models";
import { errorMessage } from "../lib/errors";
import { PRIORITY_LABEL, TASK_STATUS_LABEL, formatDate } from "../lib/format";
import { Field, FormError, SelectField, useSubmit } from "./AuthLayout";
import { FilterBar, FilterCheck, FilterSelect } from "./Filters";

interface Member {
  user_id: number;
  name: string;
}

interface Props {
  project: Project;
  userId: number;
  onProjectChange(project: Project): void;
}

const STATUS_OPTIONS = Object.entries(TASK_STATUS_LABEL).map(([value, label]) => ({ value, label }));
const STATUS_FILTERS = [{ value: "", label: "All" }, { value: "open", label: "Open" }, ...STATUS_OPTIONS];
const OPEN = (s: TaskStatus) => s !== "done" && s !== "cancelled";

export function TaskSection({ project, userId, onProjectChange }: Props) {
  const role = project.my_role ?? "viewer";
  const editable = project.status !== "archived";
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [assigneeFilter, setAssigneeFilter] = useState("");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const filtering = statusFilter !== "" || assigneeFilter !== "" || overdueOnly;

  const shown = (tasks ?? []).filter(
    (t) =>
      (statusFilter === "" || (statusFilter === "open" ? OPEN(t.status) : t.status === statusFilter)) &&
      (assigneeFilter === "" ||
        (assigneeFilter === "none" ? t.assignee_id === null : t.assignee_id === Number(assigneeFilter))) &&
      (!overdueOnly || t.is_overdue),
  );
  const assigneeOptions = [
    { value: "", label: "Anyone" },
    { value: String(userId), label: "Assigned to me" },
    { value: "none", label: "Unassigned" },
    ...members.filter((m) => m.user_id !== userId).map((m) => ({ value: String(m.user_id), label: m.name })),
  ];

  useEffect(() => {
    api<{ tasks: Task[] }>(`/projects/${project.id}/tasks`)
      .then((r) => setTasks(r.tasks))
      .catch((e) => setError(errorMessage(e, "Couldn't load tasks.")));
    api<{ members: Member[] }>(`/organizations/${project.organization_id}/members`)
      .then((r) => setMembers(r.members))
      .catch(() => setMembers([]));
  }, [project.id, project.organization_id]);

  const canChangeStatus = (t: Task) =>
    editable && (canManageProjects(role) || (role === "contributor" && t.assignee_id === userId));

  const changeStatus = async (task: Task, status: TaskStatus) => {
    setError(null);
    try {
      const r = await api<{ task: Task; project: Project }>(`/tasks/${task.id}`, { method: "PATCH", body: { status } });
      setTasks((prev) => prev?.map((t) => (t.id === task.id ? r.task : t)) ?? prev);
      onProjectChange(r.project);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <section className="projects-section" aria-labelledby="tasks-heading">
      <div className="section-head">
        <h2 id="tasks-heading">Tasks</h2>
        {canContribute(role) && editable && !adding && (
          <button type="button" className="btn btn--primary" onClick={() => setAdding(true)}>
            Add task
          </button>
        )}
      </div>

      <FormError message={error} />

      {adding && (
        <TaskForm
          project={project}
          members={members}
          onCancel={() => setAdding(false)}
          onSaved={(task, p) => {
            setAdding(false);
            setTasks((prev) => (prev ? [...prev, task].sort(byDueDate) : [task]));
            onProjectChange(p);
          }}
        />
      )}

      {tasks && tasks.length > 0 && (
        <FilterBar label="Filter tasks">
          <FilterSelect label="Status" value={statusFilter} onChange={setStatusFilter} options={STATUS_FILTERS} />
          <FilterSelect
            label="Assignee"
            value={assigneeFilter}
            onChange={setAssigneeFilter}
            options={assigneeOptions}
          />
          <FilterCheck label="Only overdue" checked={overdueOnly} onChange={setOverdueOnly} />
        </FilterBar>
      )}

      {tasks === null && !error && <p className="muted">Loading…</p>}
      {tasks && tasks.length === 0 && <p className="muted">No tasks yet. Add the first step of this project.</p>}
      {tasks && tasks.length > 0 && shown.length === 0 && filtering && (
        <p className="muted">
          No tasks match these filters.{" "}
          <button
            type="button"
            className="link-btn"
            onClick={() => {
              setStatusFilter("");
              setAssigneeFilter("");
              setOverdueOnly(false);
            }}
          >
            Clear filters
          </button>
        </p>
      )}

      {shown.length > 0 && (
        <ul className="rows">
          {shown.map((t) =>
            editingId === t.id ? (
              <li key={t.id} className="row row--editing">
                <TaskForm
                  project={project}
                  members={members}
                  task={t}
                  onCancel={() => setEditingId(null)}
                  onSaved={(task, p) => {
                    setEditingId(null);
                    setTasks((prev) => prev?.map((x) => (x.id === task.id ? task : x)).sort(byDueDate) ?? prev);
                    onProjectChange(p);
                  }}
                />
              </li>
            ) : (
              <li key={t.id} className={t.status === "done" || t.status === "cancelled" ? "row row--voided" : "row"}>
                <div className="row__main">
                  <p className="row__title">{t.title}</p>
                  <p className="row__meta">
                    {PRIORITY_LABEL[t.priority]} priority
                    {t.assignee_name ? ` — ${t.assignee_name}` : " — Unassigned"}
                    {t.due_date && (
                      <>
                        {" — "}
                        <span className={t.is_overdue ? "overdue" : undefined}>
                          {t.is_overdue ? "Overdue, was due " : "Due "}
                          {formatDate(t.due_date)}
                        </span>
                      </>
                    )}
                  </p>
                </div>
                <div className="row__side">
                  <select
                    className="status-select"
                    aria-label={`Status of ${t.title}`}
                    value={t.status}
                    disabled={!canChangeStatus(t)}
                    onChange={(e) => changeStatus(t, e.target.value as TaskStatus)}
                  >
                    {STATUS_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                  {editable && canManageProjects(role) && (
                    <button type="button" className="link-btn" onClick={() => setEditingId(t.id)}>
                      Edit
                    </button>
                  )}
                </div>
              </li>
            ),
          )}
        </ul>
      )}
    </section>
  );
}

/** Dated tasks first, soonest due first; undated last. Matches the server order. */
function byDueDate(a: Task, b: Task) {
  if (a.due_date === b.due_date) return a.id - b.id;
  if (a.due_date === null) return 1;
  if (b.due_date === null) return -1;
  return a.due_date < b.due_date ? -1 : 1;
}

function TaskForm({
  project,
  members,
  task,
  onSaved,
  onCancel,
}: {
  project: Project;
  members: Member[];
  /** Edit this task instead of adding one. */
  task?: Task;
  onSaved(task: Task, project: Project): void;
  onCancel(): void;
}) {
  const [form, setForm] = useState({
    title: task?.title ?? "",
    priority: task?.priority ?? "medium",
    due_date: task?.due_date ?? "",
    assignee_id: task?.assignee_id ? String(task.assignee_id) : "",
  });
  const id = task ? `task_${task.id}_` : "task_";
  // Keep a current assignee who has since left the organization selectable.
  const assigneeOptions = [
    { value: "", label: "Unassigned" },
    ...members.map((m) => ({ value: String(m.user_id), label: m.name })),
    ...(task?.assignee_id && !members.some((m) => m.user_id === task.assignee_id)
      ? [{ value: String(task.assignee_id), label: task.assignee_name ?? "Former member" }]
      : []),
  ];
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const set = (k: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      setFieldErrors({});
      const body = {
        title: form.title.trim(),
        priority: form.priority as TaskPriority,
        due_date: form.due_date || null,
        assignee_id: form.assignee_id ? Number(form.assignee_id) : null,
      };
      if (task && body.assignee_id === task.assignee_id) {
        // Unchanged: don't re-validate an assignee who may have left the organization.
        delete (body as Partial<typeof body>).assignee_id;
      }
      const r = task
        ? await api<{ task: Task; project: Project }>(`/tasks/${task.id}`, { method: "PATCH", body })
        : await api<{ task: Task; project: Project }>(`/projects/${project.id}/tasks`, { body });
      onSaved(r.task, r.project);
    },
    (e) => {
      if (e instanceof ApiError && e.field) setFieldErrors({ [e.field]: e.message });
      else setError(errorMessage(e));
    },
  );

  return (
    <form onSubmit={submit} className="panel form" aria-label={task ? "Edit task" : "Add task"}>
      <h3 className="panel__title">{task ? "Edit task" : "Add task"}</h3>
      <FormError message={error} />
      <Field label="Title" name={`${id}title`} value={form.title} onChange={set("title")} error={fieldErrors.title} />
      <div className="form__row">
        <SelectField
          label="Priority"
          name={`${id}priority`}
          value={form.priority}
          onChange={set("priority")}
          options={Object.entries(PRIORITY_LABEL).map(([value, label]) => ({ value, label }))}
        />
        <Field
          label="Due date"
          name={`${id}due`}
          type="date"
          value={form.due_date}
          onChange={set("due_date")}
          error={fieldErrors.due_date}
          required={false}
        />
      </div>
      <SelectField
        label="Assigned to"
        name={`${id}assignee`}
        value={form.assignee_id}
        onChange={set("assignee_id")}
        options={assigneeOptions}
      />
      {fieldErrors.assignee_id && <p className="field__message field__message--error">{fieldErrors.assignee_id}</p>}
      <div className="form__actions">
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? "Saving…" : task ? "Save changes" : "Save task"}
        </button>
        <button className="btn btn--quiet" type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
