import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import { canContribute, canManageProjects, type Expense, type Project } from "../api/models";
import { errorMessage } from "../lib/errors";
import { formatDate, formatMoney, todayIso } from "../lib/format";
import { Field, FormError, SelectField, useSubmit } from "./AuthLayout";

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
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = showVoided ? "" : "&status=valid";
  const load = useCallback(
    (offset = 0) =>
      api<{ expenses: Expense[]; total: number }>(`/projects/${project.id}/expenses?limit=${PAGE}&offset=${offset}${query}`)
        .then((r) => {
          setExpenses((prev) => (offset === 0 || !prev ? r.expenses : [...prev, ...r.expenses]));
          setTotal(r.total);
        })
        .catch((e) => setError(errorMessage(e, "Couldn't load expenses."))),
    [project.id, query],
  );

  useEffect(() => {
    load(0);
  }, [load]);

  const canChange = (e: Expense) =>
    editable && e.status === "valid" && (canManageProjects(role) || (role === "contributor" && e.created_by === userId));

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

      <label className="check">
        <input type="checkbox" checked={showVoided} onChange={(e) => setShowVoided(e.target.checked)} />
        Show voided expenses
      </label>

      {expenses === null && !error && <p className="muted">Loading…</p>}

      {expenses && expenses.length === 0 && (
        <p className="muted">
          {showVoided ? "No expenses yet." : "No expenses yet. Spending you record counts against the budget."}
        </p>
      )}

      {expenses && expenses.length > 0 && (
        <ul className="rows">
          {expenses.map((e) => (
            <ExpenseRow
              key={e.id}
              expense={e}
              canChange={canChange(e)}
              onVoided={(p, updated) => {
                onProjectChange(p);
                setError(null);
                if (showVoided) setExpenses((prev) => prev?.map((x) => (x.id === updated.id ? updated : x)) ?? prev);
                else load(0);
              }}
              onError={setError}
            />
          ))}
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
  onError,
}: {
  expense: Expense;
  canChange: boolean;
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
            <button type="button" className="link-btn" onClick={() => setConfirming(true)}>
              Void
            </button>
          ))}
      </div>
    </li>
  );
}

function ExpenseForm({
  project,
  onSaved,
  onCancel,
}: {
  project: Project;
  onSaved(project: Project): void;
  onCancel(): void;
}) {
  const [form, setForm] = useState({ category: CATEGORIES[0], amount: "", expense_date: todayIso(), description: "" });
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const set = (k: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      setFieldErrors({});
      const r = await api<{ project: Project }>(`/projects/${project.id}/expenses`, {
        body: {
          category: form.category,
          amount: form.amount.trim().replace(",", "."),
          expense_date: form.expense_date,
          description: form.description.trim() || null,
        },
      });
      onSaved(r.project);
    },
    (e) => {
      if (e instanceof ApiError && e.field) setFieldErrors({ [e.field]: e.message });
      else setError(errorMessage(e));
    },
  );

  return (
    <form onSubmit={submit} className="panel form" aria-label="Add expense">
      <h3 className="panel__title">Add expense</h3>
      <FormError message={error} />
      <div className="form__row">
        <SelectField
          label="Category"
          name="expense_category"
          value={form.category}
          onChange={set("category")}
          options={CATEGORIES.map((c) => ({ value: c, label: c }))}
        />
        <Field
          label={`Amount (${project.currency})`}
          name="expense_amount"
          value={form.amount}
          onChange={set("amount")}
          error={fieldErrors.amount}
          inputMode="decimal"
        />
      </div>
      <div className="form__row">
        <Field
          label="Date"
          name="expense_date"
          type="date"
          value={form.expense_date}
          onChange={set("expense_date")}
          error={fieldErrors.expense_date}
        />
        <Field
          label="Note"
          name="expense_note"
          value={form.description}
          onChange={set("description")}
          error={fieldErrors.description}
          required={false}
        />
      </div>
      <div className="form__actions">
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save expense"}
        </button>
        <button className="btn btn--quiet" type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
