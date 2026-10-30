import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api, download } from "../api/client";
import type { ProjectReport, ReportTask, SpendingRow } from "../api/models";
import { FormError } from "../components/AuthLayout";
import { Wordmark } from "../components/Zellij";
import { errorMessage } from "../lib/errors";
import {
  PRIORITY_LABEL,
  STATUS_LABEL,
  TASK_STATUS_LABEL,
  formatDate,
  formatDateRange,
  formatMoney,
  formatMonth,
  formatPct,
} from "../lib/format";

// The API sends definitions as an object (keys arrive sorted); show them in reading order with labels.
const DEFINITION_ORDER = ["actual", "variance", "completion", "overdue"];
const DEFINITION_LABEL: Record<string, string> = {
  actual: "Spent",
  variance: "Over/under budget",
  completion: "Task completion",
  overdue: "Overdue",
};

/** Printable project summary. Kept outside the app shell so it prints cleanly (Save as PDF from the print dialog). */
export default function Report() {
  const { projectId } = useParams();
  const [report, setReport] = useState<ProjectReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    const previousTitle = document.title;
    api<{ report: ProjectReport }>(`/projects/${projectId}/report`)
      .then((r) => {
        setReport(r.report);
        document.title = `${r.report.project.name} report`;
      })
      .catch((e) =>
        setError(
          e instanceof ApiError && e.status === 404
            ? "We couldn't find that project."
            : errorMessage(e, "Couldn't load the report."),
        ),
      );
    return () => {
      document.title = previousTitle;
    };
  }, [projectId]);

  const exportCsv = async (kind: "expenses" | "tasks") => {
    setBusy(kind);
    setError(null);
    try {
      await download(`/projects/${projectId}/${kind}.csv`, `${kind}.csv`);
    } catch (e) {
      setError(errorMessage(e, "The download failed. Try again."));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="report">
      <div className="report__toolbar no-print">
        <Link to={`/app/projects/${projectId}`} className="back">
          Back to project
        </Link>
        <div className="report__actions">
          <button type="button" className="btn btn--secondary" onClick={() => exportCsv("expenses")} disabled={!!busy}>
            {busy === "expenses" ? "Preparing…" : "Expenses CSV"}
          </button>
          <button type="button" className="btn btn--secondary" onClick={() => exportCsv("tasks")} disabled={!!busy}>
            {busy === "tasks" ? "Preparing…" : "Tasks CSV"}
          </button>
          <button type="button" className="btn btn--primary" onClick={() => window.print()} disabled={!report}>
            Print / Save as PDF
          </button>
        </div>
      </div>

      <FormError message={error} />
      {!report && !error && <p className="muted">Loading…</p>}
      {report && <ReportBody report={report} />}
    </div>
  );
}

function ReportBody({ report: r }: { report: ProjectReport }) {
  const c = r.project.currency;
  const dates = formatDateRange(r.project.start_date, r.project.end_date);
  const generated = new Date(r.generated_at).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
  const hasBudget = Number(r.budget.approved) > 0;

  return (
    <article className="report__page">
      <header className="report__header">
        <Wordmark />
        <p className="muted">
          {r.organization.name}. Report as of {formatDate(r.as_of)}, generated {generated}.
        </p>
        <h1>{r.project.name}</h1>
        <p className="main__org">
          {STATUS_LABEL[r.project.status]}
          {dates ? `. ${dates}` : ""}
          {r.project.owner ? `. Owner: ${r.project.owner}` : ""}.
        </p>
        {r.project.description && <p className="project__description">{r.project.description}</p>}
      </header>

      <section aria-labelledby="r-budget">
        <h2 id="r-budget">Budget</h2>
        <dl className="report__figures">
          <Figure label="Approved budget" value={hasBudget ? formatMoney(r.budget.approved, c) : "No budget set"} />
          <Figure label="Spent" value={formatMoney(r.budget.actual, c)} />
          <Figure label="Remaining" value={formatMoney(r.budget.remaining, c)} over={r.budget.over_budget} />
          <Figure label="Budget used" value={formatPct(r.budget.consumed_pct)} over={r.budget.over_budget} />
        </dl>
        <p className="report__note">
          {r.budget.over_budget ? `Over budget by ${formatMoney(r.budget.variance, c)}. ` : ""}
          Based on {r.budget.valid_expense_count} valid {r.budget.valid_expense_count === 1 ? "expense" : "expenses"}
          {r.budget.excluded_expense_count > 0
            ? `; ${r.budget.excluded_expense_count} voided or refunded not counted`
            : ""}
          .
        </p>
      </section>

      <section aria-labelledby="r-category">
        <h2 id="r-category">Spending by category</h2>
        <SpendingTable rows={r.spending_by_category} currency={c} groupLabel="Category" />
      </section>

      <section aria-labelledby="r-month">
        <h2 id="r-month">Spending by month</h2>
        <SpendingTable rows={r.spending_by_month} currency={c} groupLabel="Month" month />
      </section>

      <section aria-labelledby="r-tasks">
        <h2 id="r-tasks">Tasks</h2>
        {r.tasks.total === 0 ? (
          <p className="muted">No tasks recorded.</p>
        ) : (
          <>
            <p>
              {r.tasks.total} {r.tasks.total === 1 ? "task" : "tasks"}, {formatPct(r.tasks.completion_pct)} complete.{" "}
              {Object.entries(r.tasks.by_status)
                .map(([s, n]) => `${TASK_STATUS_LABEL[s]}: ${n}`)
                .join(", ")}
              .
            </p>
            <h3>Overdue</h3>
            <TaskTable tasks={r.tasks.overdue} empty="Nothing overdue." overdue />
            <h3>Due in the next 14 days</h3>
            <TaskTable tasks={r.tasks.upcoming} empty="Nothing due in the next 14 days." />
          </>
        )}
      </section>

      {r.milestones.length > 0 && (
        <section aria-labelledby="r-milestones">
          <h2 id="r-milestones">Milestones</h2>
          <table className="report__table">
            <thead>
              <tr>
                <th scope="col">Milestone</th>
                <th scope="col">Due</th>
                <th scope="col">Status</th>
                <th scope="col" className="num">
                  Tasks done
                </th>
              </tr>
            </thead>
            <tbody>
              {r.milestones.map((m, i) => (
                <tr key={i}>
                  <td>{m.title}</td>
                  <td className={m.is_overdue ? "overdue" : undefined}>
                    {m.due_date ? formatDate(m.due_date) : "—"}
                    {m.is_overdue ? " (overdue)" : ""}
                  </td>
                  <td>{m.status === "done" ? "Done" : "Open"}</td>
                  <td className="num">{m.task_count === 0 ? "No tasks" : formatPct(m.task_completion_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <footer className="report__footer">
        <h2>How figures are calculated</h2>
        <ul>
          {DEFINITION_ORDER.filter((k) => r.definitions[k]).map((k) => (
            <li key={k}>
              <strong>{DEFINITION_LABEL[k]}:</strong> {r.definitions[k]}
            </li>
          ))}
        </ul>
      </footer>
    </article>
  );
}

function Figure({ label, value, over = false }: { label: string; value: string; over?: boolean }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className={over ? "totals__value--over" : undefined}>{value}</dd>
    </div>
  );
}

function SpendingTable({
  rows,
  currency,
  groupLabel,
  month = false,
}: {
  rows: SpendingRow[];
  currency: string;
  groupLabel: string;
  month?: boolean;
}) {
  if (rows.length === 0) return <p className="muted">No valid expenses recorded.</p>;
  return (
    <table className="report__table">
      <thead>
        <tr>
          <th scope="col">{groupLabel}</th>
          <th scope="col" className="num">
            Expenses
          </th>
          <th scope="col" className="num">
            Amount
          </th>
          <th scope="col" className="num">
            Share
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.group}>
            <td>{month ? formatMonth(row.group) : row.group}</td>
            <td className="num">{row.expense_count}</td>
            <td className="num">{formatMoney(row.total, currency)}</td>
            <td className="num">{formatPct(row.share_pct)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TaskTable({ tasks, empty, overdue = false }: { tasks: ReportTask[]; empty: string; overdue?: boolean }) {
  if (tasks.length === 0) return <p className="muted">{empty}</p>;
  return (
    <table className="report__table">
      <thead>
        <tr>
          <th scope="col">Task</th>
          <th scope="col">Due</th>
          <th scope="col">Assignee</th>
          <th scope="col">Priority</th>
          <th scope="col">Status</th>
        </tr>
      </thead>
      <tbody>
        {tasks.map((t) => (
          <tr key={t.id}>
            <td>
              {t.title}
              {t.milestone && <span className="muted"> ({t.milestone})</span>}
            </td>
            <td className={overdue ? "overdue" : undefined}>
              {t.due_date ? formatDate(t.due_date) : "—"}
              {overdue && t.days_overdue !== null
                ? ` (${t.days_overdue} ${t.days_overdue === 1 ? "day" : "days"} late)`
                : ""}
            </td>
            <td>{t.assignee ?? "Unassigned"}</td>
            <td>{PRIORITY_LABEL[t.priority]}</td>
            <td>{TASK_STATUS_LABEL[t.status]}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
