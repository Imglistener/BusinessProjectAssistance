import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import { canContribute, canManageProjects, type Expense, type Project } from "../api/models";
import { errorMessage } from "../lib/errors";
import { formatDate, formatMoney, todayIso } from "../lib/format";
import { Field, FormError, SelectField, useSubmit } from "./AuthLayout";
import { FilterBar, FilterCheck, FilterDate, FilterSelect } from "./Filters";

const CATEGORIES = ["Design", "Software", "Marketing", "Equipment", "Travel", "Services", "Other"];
const PAGE = 50;

interface Props {
  project: Project;
  userId: number;
  onProjectChange(project: Project): void;
}

export function ExpenseSection({ project, userId, onProjectChange }: Props) {
  const role = project.my_role ?? "viewer";
  const editable = project.status !== "archived";
  const [expenses, setExpenses] = useState<Expense[] | null>(null);
  const [total, setTotal] = useState(0);
  const [showVoided, setShowVoided] = useState(false);
  const [category, setCategory] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [categories, setCategories] = useState<string[]>([]);
  const [matching, setMatching] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const filtering = category !== "" || from !== "" || to !== "";

  const params = new URLSearchParams();
  if (!showVoided) params.set("status", "valid");
  if (category) params.set("category", category);
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  const query = params.toString();

  const load = useCallback(
    (offset = 0) =>
      api<{ expenses: Expense[]; total: number; matching_amount: string; categories: string[] }>(
        `/projects/${project.id}/expenses?limit=${PAGE}&offset=${offset}&${query}`,
      )
        .then((r) => {
          setError(null);
          setExpenses((prev) => (offset === 0 || !prev ? r.expenses : [...prev, ...r.expenses]));
          setTotal(r.total);
          setMatching(r.matching_amount);
          setCategories(r.categories);
        })
        .catch((e) => setError(errorMessage(e, "Couldn't load expenses."))),
    [project.id, query],
  );

  useEffect(() => {
    load(0);
  }, [load]);

  const canChange = (e: Expense) =>
    editable &&
    e.status === "valid" &&
    (canManageProjects(role) || (role === "contributor" && e.created_by === userId));

  return (
    <section className="projects-section" aria-labelledby="expenses-heading">
      <div className="section-head">
        <h2 id="expenses-heading">Expenses</h2>
        {canContribute(role) && editable && !adding && (
          <button type="button" className="btn btn--primary" onClick={() => setAdding(true)}>
            Add expense
          </button>
        )}
      </div>

      <FormError message={error} />

      {adding && (
        <ExpenseForm
          project={project}
          onCancel={() => setAdding(false)}
          onSaved={(p) => {
            setAdding(false);
            onProjectChange(p);
            load(0);
          }}
        />
      )}

      <FilterBar label="Filter expenses">
        <FilterSelect
          label="Category"
          value={category}
          onChange={setCategory}
          options={[{ value: "", label: "All categories" }, ...categories.map((c) => ({ value: c, label: c }))]}
        />
        <FilterDate label="From" value={from} onChange={setFrom} />
        <FilterDate label="To" value={to} onChange={setTo} />
        <FilterCheck label="Show voided" checked={showVoided} onChange={setShowVoided} />
      </FilterBar>

      {filtering && expenses && matching !== null && (
        <p className="filters__summary" role="status">
          {total} {total === 1 ? "expense" : "expenses"} match. Valid total: {formatMoney(matching, project.currency)}.{" "}
          <button
            type="button"
            className="link-btn"
            onClick={() => {
              setCategory("");
              setFrom("");
              setTo("");
            }}
          >
            Clear filters
          </button>
        </p>
      )}

      {expenses === null && !error && <p className="muted">Loading…</p>}

      {expenses && expenses.length === 0 && (
        <p className="muted">
          {filtering
            ? "No expenses match these filters."
            : showVoided
              ? "No expenses yet."
              : "No expenses yet. Spending you record counts against the budget."}
        </p>
      )}

      {expenses && expenses.length > 0 && (
        <ul className="rows">
          {expenses.map((e) =>
            editingId === e.id ? (
              <li key={e.id} className="row row--editing">
                <ExpenseForm
                  project={project}
                  expense={e}
                  onCancel={() => setEditingId(null)}
                  onSaved={(p) => {
                    setEditingId(null);
                    onProjectChange(p);
                    load(0);
                  }}
                />
              </li>
            ) : (
              <ExpenseRow
                key={e.id}
                expense={e}
                canChange={canChange(e)}
                onEdit={() => setEditingId(e.id)}
                onVoided={(p, updated) => {
                  onProjectChange(p);
                  setError(null);
                  if (showVoided) setExpenses((prev) => prev?.map((x) => (x.id === updated.id ? updated : x)) ?? prev);
                  else load(0);
                }}
                onError={setError}
              />
            ),
          )}
        </ul>
      )}

      {expenses && expenses.length < total && (
        <button type="button" className="btn btn--quiet" onClick={() => load(expenses.length)}>
          Show more
        </button>
      )}
    </section>
  );
}

function ExpenseRow({
  expense,
  canChange,
  onVoided,
  onEdit,
  onError,
}: {
  expense: Expense;
  canChange: boolean;
  onEdit(): void;
  onVoided(project: Project, expense: Expense): void;
  onError(message: string): void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const voided = expense.status !== "valid";

  const doVoid = async () => {
    setBusy(true);
    try {
      const r = await api<{ expense: Expense; project: Project }>(`/expenses/${expense.id}/void`, { method: "POST" });
      onVoided(r.project, r.expense);
    } catch (e) {
      onError(errorMessage(e));
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  };

  return (
    <li className={voided ? "row row--voided" : "row"}>
      <div className="row__main">
        <p className="row__title">
          {expense.category}
          {voided && <span className="tag">{expense.status === "voided" ? "Voided" : "Refunded"}</span>}
        </p>
        <p className="row__meta">
          {formatDate(expense.expense_date)}
          {expense.description ? ` — ${expense.description}` : ""}
        </p>
      </div>
      <div className="row__side">
        <span className="row__amount">{formatMoney(expense.amount, expense.currency)}</span>
        {canChange &&
          (confirming ? (
            <span className="row__confirm">
              <button type="button" className="link-btn link-btn--danger" onClick={doVoid} disabled={busy}>
                {busy ? "Voiding…" : "Void expense"}
              </button>
              <button type="button" className="link-btn" onClick={() => setConfirming(false)} disabled={busy}>
                Keep
              </button>
            </span>
          ) : (
            <span className="row__confirm">
              <button type="button" className="link-btn" onClick={onEdit}>
                Edit
              </button>
              <button type="button" className="link-btn" onClick={() => setConfirming(true)}>
                Void
              </button>
            </span>
          ))}
      </div>
    </li>
  );
}

function ExpenseForm({
  project,
  expense,
  onSaved,
  onCancel,
}: {
  project: Project;
  /** Edit this expense instead of adding one. */
  expense?: Expense;
  onSaved(project: Project): void;
  onCancel(): void;
}) {
  const [form, setForm] = useState({
    category: expense?.category ?? CATEGORIES[0],
    amount: expense?.amount ?? "",
    expense_date: expense?.expense_date ?? todayIso(),
    description: expense?.description ?? "",
  });
  // Unique field ids when an edit form and the add form are open together.
  const id = expense ? `expense_${expense.id}_` : "expense_";
  const categoryOptions = [...new Set([...CATEGORIES, form.category])].map((c) => ({ value: c, label: c }));
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const set = (k: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      setFieldErrors({});
      const body = {
        category: form.category,
        amount: form.amount.trim().replace(",", "."),
        expense_date: form.expense_date,
        description: form.description.trim() || null,
      };
      const r = expense
        ? await api<{ project: Project }>(`/expenses/${expense.id}`, { method: "PATCH", body })
        : await api<{ project: Project }>(`/projects/${project.id}/expenses`, { body });
      onSaved(r.project);
    },
    (e) => {
      if (e instanceof ApiError && e.field) setFieldErrors({ [e.field]: e.message });
      else setError(errorMessage(e));
    },
  );

  return (
    <form onSubmit={submit} className="panel form" aria-label={expense ? "Edit expense" : "Add expense"}>
      <h3 className="panel__title">{expense ? "Edit expense" : "Add expense"}</h3>
      <FormError message={error} />
      <div className="form__row">
        <SelectField
          label="Category"
          name={`${id}category`}
          value={form.category}
          onChange={set("category")}
          options={categoryOptions}
        />
        <Field
          label={`Amount (${project.currency})`}
          name={`${id}amount`}
          value={form.amount}
          onChange={set("amount")}
          error={fieldErrors.amount}
          inputMode="decimal"
        />
      </div>
      <div className="form__row">
        <Field
          label="Date"
          name={`${id}date`}
          type="date"
          value={form.expense_date}
          onChange={set("expense_date")}
          error={fieldErrors.expense_date}
        />
        <Field
          label="Note"
          name={`${id}note`}
          value={form.description}
          onChange={set("description")}
          error={fieldErrors.description}
          required={false}
        />
      </div>
      <div className="form__actions">
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? "Saving…" : expense ? "Save changes" : "Save expense"}
        </button>
        <button className="btn btn--quiet" type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
