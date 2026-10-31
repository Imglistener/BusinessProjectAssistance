import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import { canContribute, canManageProjects, type Expense, type Project, type Trip } from "../api/models";
import { errorMessage } from "../lib/errors";
import { formatDate, formatMoney, todayIso } from "../lib/format";
import { Field, FormError, SelectField, useSubmit } from "./AuthLayout";
import { ExpenseFiles } from "./ExpenseFiles";
import { FilterBar, FilterCheck, FilterDate, FilterSelect } from "./Filters";
import { t } from "../i18n";

const CATEGORIES = ["Design", "Software", "Marketing", "Equipment", "Travel", "Services", "Other"];
const PAGE = 50;

interface Props {
  project: Project;
  userId: number;
  /** Trips on the project, so an expense can be linked to one. */
  trips: Trip[];
  onProjectChange(project: Project): void;
}

export function ExpenseSection({ project, userId, trips, onProjectChange }: Props) {
  const tripTitle = new Map(trips.map((x) => [x.id, x.title]));
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
        .catch((e) => setError(errorMessage(e, t("Couldn't load expenses.")))),
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
        <h2 id="expenses-heading">{t("Expenses")}</h2>
        {canContribute(role) && editable && !adding && (
          <button type="button" className="btn btn--primary" onClick={() => setAdding(true)}>
            {t("Add expense")}
          </button>
        )}
      </div>

      <FormError message={error} />

      {adding && (
        <ExpenseForm
          project={project}
          trips={trips}
          onCancel={() => setAdding(false)}
          onSaved={(p) => {
            setAdding(false);
            onProjectChange(p);
            load(0);
          }}
        />
      )}

      <FilterBar label={t("Filter expenses")}>
        <FilterSelect
          label={t("Category")}
          value={category}
          onChange={setCategory}
          options={[{ value: "", label: t("All categories") }, ...categories.map((c) => ({ value: c, label: c }))]}
        />
        <FilterDate label={t("From")} value={from} onChange={setFrom} />
        <FilterDate label={t("To")} value={to} onChange={setTo} />
        <FilterCheck label={t("Show voided")} checked={showVoided} onChange={setShowVoided} />
      </FilterBar>

      {filtering && expenses && matching !== null && (
        <p className="filters__summary" role="status">
          {t("{count} expenses match. Valid total: {amount}.", { count: total, amount: formatMoney(matching, project.currency) })}{" "}
          <button
            type="button"
            className="link-btn"
            onClick={() => {
              setCategory("");
              setFrom("");
              setTo("");
            }}
          >
            {t("Clear filters")}
          </button>
        </p>
      )}

      {expenses === null && !error && <p className="muted">{t("Loading…")}</p>}

      {expenses && expenses.length === 0 && (
        <p className="muted">
          {filtering
            ? t("No expenses match these filters.")
            : showVoided
              ? t("No expenses yet.")
              : t("No expenses yet. Spending you record counts against the budget.")}
        </p>
      )}

      {expenses && expenses.length > 0 && (
        <ul className="rows">
          {expenses.map((e) =>
            editingId === e.id ? (
              <li key={e.id} className="row row--editing">
                <ExpenseForm
                  project={project}
                  trips={trips}
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
                tripTitle={e.trip_id ? tripTitle.get(e.trip_id) : undefined}
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
          {t("Show more")}
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
  tripTitle,
}: {
  expense: Expense;
  canChange: boolean;
  tripTitle?: string;
  onEdit(): void;
  onVoided(project: Project, expense: Expense): void;
  onError(message: string): void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [showFiles, setShowFiles] = useState(false);
  const [fileCount, setFileCount] = useState(expense.attachment_count);
  const voided = expense.status !== "valid";
  // Voided expenses keep their receipts (viewable) but take no new ones.
  const canChangeFiles = canChange && !voided;

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
    <li className={voided ? "row row--voided row--stacked" : "row row--stacked"}>
      <div className="row row--plain">
        <div className="row__main">
          <p className="row__title">
            {expense.category}
            {voided && <span className="tag">{expense.status === "voided" ? t("Voided") : t("Refunded")}</span>}
          </p>
          <p className="row__meta">
            {formatDate(expense.expense_date)}
            {expense.description ? ` — ${expense.description}` : ""}
            {tripTitle ? ` — ${t("Trip: {title}", { title: tripTitle })}` : ""}
          </p>
        </div>
        <div className="row__side">
          <span className="row__amount">{formatMoney(expense.amount, expense.currency)}</span>
          {(fileCount > 0 || canChangeFiles) && (
            <button
              type="button"
              className="link-btn"
              aria-expanded={showFiles}
              onClick={() => setShowFiles((s) => !s)}
            >
              {fileCount > 0 ? t("Receipts ({count})", { count: fileCount }) : t("Add receipt")}
            </button>
          )}
          {canChange &&
            (confirming ? (
              <span className="row__confirm">
                <button type="button" className="link-btn link-btn--danger" onClick={doVoid} disabled={busy}>
                  {busy ? t("Voiding…") : t("Void expense")}
                </button>
                <button type="button" className="link-btn" onClick={() => setConfirming(false)} disabled={busy}>
                  {t("Keep")}
                </button>
              </span>
            ) : (
              <span className="row__confirm">
                <button type="button" className="link-btn" onClick={onEdit}>
                  {t("Edit")}
                </button>
                <button type="button" className="link-btn" onClick={() => setConfirming(true)}>
                  {t("Void")}
                </button>
              </span>
            ))}
        </div>
      </div>
      {showFiles && <ExpenseFiles expenseId={expense.id} canChange={canChangeFiles} onCountChange={setFileCount} />}
    </li>
  );
}

function ExpenseForm({
  project,
  trips,
  expense,
  onSaved,
  onCancel,
}: {
  project: Project;
  trips: Trip[];
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
    trip_id: expense?.trip_id ? String(expense.trip_id) : "",
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
        trip_id: form.trip_id ? Number(form.trip_id) : null,
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
    <form onSubmit={submit} className="panel form" aria-label={expense ? t("Edit expense") : t("Add expense")}>
      <h3 className="panel__title">{expense ? t("Edit expense") : t("Add expense")}</h3>
      <FormError message={error} />
      <div className="form__row">
        <SelectField
          label={t("Category")}
          name={`${id}category`}
          value={form.category}
          onChange={set("category")}
          options={categoryOptions}
        />
        <Field
          label={t("Amount ({currency})", { currency: project.currency })}
          name={`${id}amount`}
          value={form.amount}
          onChange={set("amount")}
          error={fieldErrors.amount}
          inputMode="decimal"
        />
      </div>
      <div className="form__row">
        <Field
          label={t("Date")}
          name={`${id}date`}
          type="date"
          value={form.expense_date}
          onChange={set("expense_date")}
          error={fieldErrors.expense_date}
        />
        <Field
          label={t("Note")}
          name={`${id}note`}
          value={form.description}
          onChange={set("description")}
          error={fieldErrors.description}
          required={false}
        />
      </div>
      {trips.length > 0 && (
        <SelectField
          label={t("Trip")}
          name={`${id}trip`}
          value={form.trip_id}
          onChange={set("trip_id")}
          options={[
            { value: "", label: t("Not for a trip") },
            ...trips.map((x) => ({ value: String(x.id), label: x.title })),
          ]}
        />
      )}
      {fieldErrors.trip_id && <p className="field__message field__message--error">{fieldErrors.trip_id}</p>}
      <div className="form__actions">
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? t("Saving…") : expense ? t("Save changes") : t("Save expense")}
        </button>
        <button className="btn btn--quiet" type="button" onClick={onCancel}>
          {t("Cancel")}
        </button>
      </div>
    </form>
  );
}
