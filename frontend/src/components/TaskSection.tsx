import { useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import {
  canContribute,
  canManageProjects,
  type Milestone,
  type Project,
  type Task,
  type TaskPriority,
  type TaskStatus,
} from "../api/models";
import { errorMessage } from "../lib/errors";
import { PRIORITY_LABEL, TASK_STATUS_LABEL, formatDate } from "../lib/format";
import { Field, FormError, SelectField, useSubmit } from "./AuthLayout";
import { FilterBar, FilterCheck, FilterSelect } from "./Filters";
import { t } from "../i18n";

interface Member {
  user_id: number;
  name: string;
}

interface Props {
  project: Project;
  userId: number;
  milestones: Milestone[];
  onProjectChange(project: Project): void;
}

const STATUS_OPTIONS = Object.entries(TASK_STATUS_LABEL).map(([value, label]) => ({ value, label }));
const STATUS_FILTERS = [{ value: "", label: t("All") }, { value: "open", label: t("Open") }, ...STATUS_OPTIONS];
const OPEN = (s: TaskStatus) => s !== "done" && s !== "cancelled";

export function TaskSection({ project, userId, milestones, onProjectChange }: Props) {
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
  const [milestoneFilter, setMilestoneFilter] = useState("");
  const filtering = statusFilter !== "" || assigneeFilter !== "" || overdueOnly || milestoneFilter !== "";
  const milestoneTitle = new Map(milestones.map((m) => [m.id, m.title]));

  const shown = (tasks ?? []).filter(
    (x) =>
      (statusFilter === "" || (statusFilter === "open" ? OPEN(x.status) : x.status === statusFilter)) &&
      (assigneeFilter === "" ||
        (assigneeFilter === "none" ? x.assignee_id === null : x.assignee_id === Number(assigneeFilter))) &&
      (!overdueOnly || x.is_overdue) &&
      (milestoneFilter === "" ||
        (milestoneFilter === "none" ? x.milestone_id === null : x.milestone_id === Number(milestoneFilter))),
  );
  const assigneeOptions = [
    { value: "", label: t("Anyone") },
    { value: String(userId), label: t("Assigned to me") },
    { value: "none", label: t("Unassigned") },
    ...members.filter((m) => m.user_id !== userId).map((m) => ({ value: String(m.user_id), label: m.name })),
  ];

  useEffect(() => {
    api<{ tasks: Task[] }>(`/projects/${project.id}/tasks`)
      .then((r) => setTasks(r.tasks))
      .catch((e) => setError(errorMessage(e, t("Couldn't load tasks."))));
    api<{ members: Member[] }>(`/organizations/${project.organization_id}/members`)
      .then((r) => setMembers(r.members))
      .catch(() => setMembers([]));
  }, [project.id, project.organization_id]);

  const canChangeStatus = (x: Task) =>
    editable && (canManageProjects(role) || (role === "contributor" && x.assignee_id === userId));

  const changeStatus = async (task: Task, status: TaskStatus) => {
    setError(null);
    try {
      const r = await api<{ task: Task; project: Project }>(`/tasks/${task.id}`, { method: "PATCH", body: { status } });
      setTasks((prev) => prev?.map((x) => (x.id === task.id ? r.task : x)) ?? prev);
      onProjectChange(r.project);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <section className="projects-section" aria-labelledby="tasks-heading">
      <div className="section-head">
        <h2 id="tasks-heading">{t("Tasks")}</h2>
        {canContribute(role) && editable && !adding && (
          <button type="button" className="btn btn--primary" onClick={() => setAdding(true)}>
            {t("Add task")}
          </button>
        )}
      </div>

      <FormError message={error} />

      {adding && (
        <TaskForm
          project={project}
          members={members}
          milestones={milestones}
          onCancel={() => setAdding(false)}
          onSaved={(task, p) => {
            setAdding(false);
            setTasks((prev) => (prev ? [...prev, task].sort(byDueDate) : [task]));
            onProjectChange(p);
          }}
        />
      )}

      {tasks && tasks.length > 0 && (
        <FilterBar label={t("Filter tasks")}>
          <FilterSelect label={t("Status")} value={statusFilter} onChange={setStatusFilter} options={STATUS_FILTERS} />
          <FilterSelect
            label={t("Assignee")}
            value={assigneeFilter}
            onChange={setAssigneeFilter}
            options={assigneeOptions}
          />
          {milestones.length > 0 && (
            <FilterSelect
              label={t("Milestone")}
              value={milestoneFilter}
              onChange={setMilestoneFilter}
              options={[
                { value: "", label: t("Any") },
                { value: "none", label: t("No milestone") },
                ...milestones.map((m) => ({ value: String(m.id), label: m.title })),
              ]}
            />
          )}
          <FilterCheck label={t("Only overdue")} checked={overdueOnly} onChange={setOverdueOnly} />
        </FilterBar>
      )}

      {tasks === null && !error && <p className="muted">{t("Loading…")}</p>}
      {tasks && tasks.length === 0 && <p className="muted">{t("No tasks yet. Add the first step of this project.")}</p>}
      {tasks && tasks.length > 0 && shown.length === 0 && filtering && (
        <p className="muted">
          {t("No tasks match these filters.")}{" "}
          <button
            type="button"
            className="link-btn"
            onClick={() => {
              setStatusFilter("");
              setAssigneeFilter("");
              setOverdueOnly(false);
              setMilestoneFilter("");
            }}
          >
            {t("Clear filters")}
          </button>
        </p>
      )}

      {shown.length > 0 && (
        <ul className="rows">
          {shown.map((x) =>
            editingId === x.id ? (
              <li key={x.id} className="row row--editing">
                <TaskForm
                  project={project}
                  members={members}
                  milestones={milestones}
                  task={x}
                  onCancel={() => setEditingId(null)}
                  onSaved={(task, p) => {
                    setEditingId(null);
                    setTasks((prev) => prev?.map((x) => (x.id === task.id ? task : x)).sort(byDueDate) ?? prev);
                    onProjectChange(p);
                  }}
                />
              </li>
            ) : (
              <li key={x.id} className={x.status === "done" || x.status === "cancelled" ? "row row--voided" : "row"}>
                <div className="row__main">
                  <p className="row__title">{x.title}</p>
                  <p className="row__meta">
                    {t("{priority} priority", { priority: PRIORITY_LABEL[x.priority] })} — {x.assignee_name ?? t("Unassigned")}
                    {x.milestone_id !== null &&
                      milestoneTitle.has(x.milestone_id) &&
                      ` — ${milestoneTitle.get(x.milestone_id)}`}
                    {x.due_date && (
                      <>
                        {" — "}
                        <span className={x.is_overdue ? "overdue" : undefined}>
                          {x.is_overdue
                            ? t("Overdue, was due {date}", { date: formatDate(x.due_date) })
                            : t("Due {date}", { date: formatDate(x.due_date) })}
                        </span>
                      </>
                    )}
                  </p>
                </div>
                <div className="row__side">
                  <select
                    className="status-select"
                    aria-label={t("Status of {title}", { title: x.title })}
                    value={x.status}
                    disabled={!canChangeStatus(x)}
                    onChange={(e) => changeStatus(x, e.target.value as TaskStatus)}
                  >
                    {STATUS_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                  {editable && canManageProjects(role) && (
                    <button type="button" className="link-btn" onClick={() => setEditingId(x.id)}>
                      {t("Edit")}
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
  milestones,
  task,
  onSaved,
  onCancel,
}: {
  project: Project;
  members: Member[];
  milestones: Milestone[];
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
    milestone_id: task?.milestone_id ? String(task.milestone_id) : "",
  });
  const id = task ? `task_${task.id}_` : "task_";
  // Keep a current assignee who has since left the organization selectable.
  const assigneeOptions = [
    { value: "", label: t("Unassigned") },
    ...members.map((m) => ({ value: String(m.user_id), label: m.name })),
    ...(task?.assignee_id && !members.some((m) => m.user_id === task.assignee_id)
      ? [{ value: String(task.assignee_id), label: task.assignee_name ?? t("Former member") }]
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
        milestone_id: form.milestone_id ? Number(form.milestone_id) : null,
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
    <form onSubmit={submit} className="panel form" aria-label={task ? t("Edit task") : t("Add task")}>
      <h3 className="panel__title">{task ? t("Edit task") : t("Add task")}</h3>
      <FormError message={error} />
      <Field label={t("Title")} name={`${id}title`} value={form.title} onChange={set("title")} error={fieldErrors.title} />
      <div className="form__row">
        <SelectField
          label={t("Priority")}
          name={`${id}priority`}
          value={form.priority}
          onChange={set("priority")}
          options={Object.entries(PRIORITY_LABEL).map(([value, label]) => ({ value, label }))}
        />
        <Field
          label={t("Due date")}
          name={`${id}due`}
          type="date"
          value={form.due_date}
          onChange={set("due_date")}
          error={fieldErrors.due_date}
          required={false}
        />
      </div>
      <SelectField
        label={t("Assigned to")}
        name={`${id}assignee`}
        value={form.assignee_id}
        onChange={set("assignee_id")}
        options={assigneeOptions}
      />
      {fieldErrors.assignee_id && <p className="field__message field__message--error">{fieldErrors.assignee_id}</p>}
      {milestones.length > 0 && (
        <SelectField
          label={t("Milestone")}
          name={`${id}milestone`}
          value={form.milestone_id}
          onChange={set("milestone_id")}
          options={[{ value: "", label: t("None") }, ...milestones.map((m) => ({ value: String(m.id), label: m.title }))]}
        />
      )}
      {fieldErrors.milestone_id && <p className="field__message field__message--error">{fieldErrors.milestone_id}</p>}
      <div className="form__actions">
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? t("Saving…") : task ? t("Save changes") : t("Save task")}
        </button>
        <button className="btn btn--quiet" type="button" onClick={onCancel}>
          {t("Cancel")}
        </button>
      </div>
    </form>
  );
}
