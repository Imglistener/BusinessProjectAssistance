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
import { getLocale, t } from "../i18n";

// The API sends definitions as an object (keys arrive sorted); show them in reading order with labels.
const DEFINITION_ORDER = ["actual", "variance", "completion", "overdue"];
const DEFINITION_LABEL: Record<string, string> = {
  actual: t("Spent"),
  variance: t("Over/under budget"),
  completion: t("Task completion"),
  overdue: t("Overdue"),
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
            ? t("We couldn't find that project.")
            : errorMessage(e, t("Couldn't load the report.")),
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
      setError(errorMessage(e, t("The download failed. Try again.")));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="report">
      <div className="report__toolbar no-print">
        <Link to={`/app/projects/${projectId}`} className="back">
          {t("Back to project")}
        </Link>
        <div className="report__actions">
          <button type="button" className="btn btn--secondary" onClick={() => exportCsv("expenses")} disabled={!!busy}>
            {busy === "expenses" ? t("Preparing…") : t("Expenses CSV")}
          </button>
          <button type="button" className="btn btn--secondary" onClick={() => exportCsv("tasks")} disabled={!!busy}>
            {busy === "tasks" ? t("Preparing…") : t("Tasks CSV")}
          </button>
          <button type="button" className="btn btn--primary" onClick={() => window.print()} disabled={!report}>
            {t("Print / Save as PDF")}
          </button>
        </div>
      </div>

      <FormError message={error} />
      {!report && !error && <p className="muted">{t("Loading…")}</p>}
      {report && <ReportBody report={report} />}
    </div>
  );
}

function ReportBody({ report: r }: { report: ProjectReport }) {
  const c = r.project.currency;
  const dates = formatDateRange(r.project.start_date, r.project.end_date);
  const generated = new Date(r.generated_at).toLocaleString(getLocale(), { dateStyle: "medium", timeStyle: "short" });
  const hasBudget = Number(r.budget.approved) > 0;

  return (
    <article className="report__page">
      <header className="report__header">
        <Wordmark />
        <p className="muted">
          {r.organization.name}.{" "}
          {t("Report as of {date}, generated {generated}.", { date: formatDate(r.as_of), generated })}
        </p>
        <h1>{r.project.name}</h1>
        <p className="main__org">
          {STATUS_LABEL[r.project.status]}
          {dates ? `. ${dates}` : ""}
          {r.project.owner ? `. ${t("Owner: {owner}", { owner: r.project.owner })}` : ""}.
        </p>
        {r.project.description && <p className="project__description">{r.project.description}</p>}
      </header>

      <section aria-labelledby="r-budget">
        <h2 id="r-budget">{t("Budget")}</h2>
        <dl className="report__figures">
          <Figure label={t("Approved budget")} value={hasBudget ? formatMoney(r.budget.approved, c) : t("No budget set")} />
          <Figure label={t("Spent")} value={formatMoney(r.budget.actual, c)} />
          <Figure label={t("Remaining")} value={formatMoney(r.budget.remaining, c)} over={r.budget.over_budget} />
          <Figure label={t("Budget used")} value={formatPct(r.budget.consumed_pct)} over={r.budget.over_budget} />
        </dl>
        <p className="report__note">
          {r.budget.over_budget ? `${t("Over budget by {amount}.", { amount: formatMoney(r.budget.variance, c) })} ` : ""}
          {r.budget.excluded_expense_count > 0
            ? t("Based on {count} valid expenses; {excluded} voided or refunded not counted.", {
                count: r.budget.valid_expense_count,
                excluded: r.budget.excluded_expense_count,
              })
            : t("Based on {count} valid expenses.", { count: r.budget.valid_expense_count })}
        </p>
      </section>

      <section aria-labelledby="r-category">
        <h2 id="r-category">{t("Spending by category")}</h2>
        <SpendingTable rows={r.spending_by_category} currency={c} groupLabel="Category" />
      </section>

      <section aria-labelledby="r-month">
        <h2 id="r-month">{t("Spending by month")}</h2>
        <SpendingTable rows={r.spending_by_month} currency={c} groupLabel="Month" month />
      </section>

      <section aria-labelledby="r-tasks">
        <h2 id="r-tasks">{t("Tasks")}</h2>
        {r.tasks.total === 0 ? (
          <p className="muted">{t("No tasks recorded.")}</p>
        ) : (
          <>
            <p>
              {t("{count} tasks, {pct} complete.", { count: r.tasks.total, pct: formatPct(r.tasks.completion_pct) })}{" "}
              {Object.entries(r.tasks.by_status)
                .map(([s, n]) => `${TASK_STATUS_LABEL[s]}: ${n}`)
                .join(", ")}
              .
            </p>
            <h3>{t("Overdue")}</h3>
            <TaskTable tasks={r.tasks.overdue} empty={t("Nothing overdue.")} overdue />
            <h3>{t("Due in the next 14 days")}</h3>
            <TaskTable tasks={r.tasks.upcoming} empty={t("Nothing due in the next 14 days.")} />
          </>
        )}
      </section>

      {r.milestones.length > 0 && (
        <section aria-labelledby="r-milestones">
          <h2 id="r-milestones">{t("Milestones")}</h2>
          <table className="report__table">
            <thead>
              <tr>
                <th scope="col">{t("Milestone")}</th>
                <th scope="col">{t("Due")}</th>
                <th scope="col">{t("Status")}</th>
                <th scope="col" className="num">
                  {t("Tasks done")}
                </th>
              </tr>
            </thead>
            <tbody>
              {r.milestones.map((m, i) => (
                <tr key={i}>
                  <td>{m.title}</td>
                  <td className={m.is_overdue ? "overdue" : undefined}>
                    {m.due_date ? formatDate(m.due_date) : "—"}
                    {m.is_overdue ? ` (${t("overdue")})` : ""}
                  </td>
                  <td>{m.status === "done" ? t("Done") : t("Open")}</td>
                  <td className="num">{m.task_count === 0 ? t("No tasks") : formatPct(m.task_completion_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <footer className="report__footer">
        <h2>{t("How figures are calculated")}</h2>
        <ul>
          {DEFINITION_ORDER.filter((k) => r.definitions[k]).map((k) => (
            <li key={k}>
              <strong>{t("{label}:", { label: DEFINITION_LABEL[k] })}</strong> {r.definitions[k]}
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
  if (rows.length === 0) return <p className="muted">{t("No valid expenses recorded.")}</p>;
  return (
    <table className="report__table">
      <thead>
        <tr>
          <th scope="col">{groupLabel}</th>
          <th scope="col" className="num">
            {t("Expenses")}
          </th>
          <th scope="col" className="num">
            {t("Amount")}
          </th>
          <th scope="col" className="num">
            {t("Share")}
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
          <th scope="col">{t("Task")}</th>
          <th scope="col">{t("Due")}</th>
          <th scope="col">{t("Assignee")}</th>
          <th scope="col">{t("Priority")}</th>
          <th scope="col">{t("Status")}</th>
        </tr>
      </thead>
      <tbody>
        {tasks.map((x) => (
          <tr key={x.id}>
            <td>
              {x.title}
              {x.milestone && <span className="muted"> ({x.milestone})</span>}
            </td>
            <td className={overdue ? "overdue" : undefined}>
              {x.due_date ? formatDate(x.due_date) : "—"}
              {overdue && x.days_overdue !== null
                ? ` (${t("{count} days late", { count: x.days_overdue })})`
                : ""}
            </td>
            <td>{x.assignee ?? t("Unassigned")}</td>
            <td>{PRIORITY_LABEL[x.priority]}</td>
            <td>{TASK_STATUS_LABEL[x.status]}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
