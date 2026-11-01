import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { canManageProjects, type Organization, type Project, type ProjectPlan } from "../api/models";
import { errorMessage } from "../lib/errors";
import { PRIORITY_LABEL, formatDate, formatMoney, formatNumber } from "../lib/format";
import { FormError } from "./AuthLayout";
import { t } from "../i18n";
import { tx } from "../i18n/rich";

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
  const stockLines = plan.inventory ?? [];
  const [keepStock, setKeepStock] = useState(() => stockLines.map(() => true));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Project | null>(null);
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  if (created) {
    return (
      <div className="proposal proposal--done" role="status">
        <p>
          {tx("{name} was created with {milestones} milestones and {tasks} tasks.", {
            name: <strong>{created.name}</strong>,
            milestones: keepMilestone.filter(Boolean).length,
            tasks: keepTask.filter(Boolean).length,
          })}
        </p>
        <Link className="btn btn--primary btn--link" to={`/app/projects/${created.id}`}>
          {t("Open the project")}
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
            .map((x) => ({ ...x, milestone: x.milestone && kept.has(x.milestone.toLowerCase()) ? x.milestone : null })),
          inventory: stockLines.filter((_, i) => keepStock[i]),
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
    <section className="proposal" aria-label={t("Draft project: {name}", { name: plan.name })}>
      <header className="proposal__head">
        <span className="tag">{t("Draft project — not created yet")}</span>
        <p className="muted">{t("Review and adjust, then create it. Untick anything you don't want.")}</p>
      </header>
      <FormError message={error} />

      <div className="proposal__fields">
        <label className="filter proposal__name">
          <span className="filter__label">{t("Name")}</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={200} />
        </label>
        <label className="filter">
          <span className="filter__label">{t("Budget ({currency})", { currency: plan.currency })}</span>
          <input value={budget} inputMode="decimal" onChange={(e) => setBudget(e.target.value)} placeholder={t("None")} />
        </label>
        <label className="filter">
          <span className="filter__label">{t("Start")}</span>
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </label>
        <label className="filter">
          <span className="filter__label">{t("End")}</span>
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </label>
      </div>
      {plan.description && <p className="proposal__description">{plan.description}</p>}

      <div className="proposal__lists">
        {plan.milestones.length > 0 && (
          <div>
            <h4>{t("Milestones")}</h4>
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
            <h4>{t("Tasks")}</h4>
            <ul>
              {plan.tasks.map((x, i) => (
                <li key={`${x.title}-${i}`}>
                  <label className="check">
                    <input type="checkbox" checked={keepTask[i]} onChange={() => toggle(setKeepTask, i)} />
                    <span>
                      {x.title}
                      <span className="muted">
                        {" — "}
                        {PRIORITY_LABEL[x.priority]}
                        {x.due_date ? `${t(", ")}${t("due {date}", { date: formatDate(x.due_date) })}` : ""}
                        {x.milestone ? `${t(", ")}${x.milestone}` : ""}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
        )}
        {stockLines.length > 0 && (
          <div>
            <h4>{t("Opening inventory")}</h4>
            <ul>
              {stockLines.map((x, i) => (
                <li key={`${x.name}-${i}`}>
                  <label className="check">
                    <input type="checkbox" checked={keepStock[i]} onChange={() => toggle(setKeepStock, i)} />
                    <span>
                      {x.name}
                      <span className="muted">
                        {" — "}
                        {x.quantity ? `${formatNumber(x.quantity)} ${x.unit}` : x.unit}
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
            {busy ? t("Creating…") : t("Create project")}
          </button>
        ) : (
          <p className="muted">
            {t("Only owners and project managers can create projects. Share this draft with one of them.")}
          </p>
        )}
        <button type="button" className="btn btn--quiet" onClick={() => setDismissed(true)}>
          {t("Dismiss")}
        </button>
      </div>
      {plan.budget && (
        <p className="muted proposal__note">
          {t("Budget drafted from the description: {amount}. Check it before creating.", {
            amount: formatMoney(plan.budget, plan.currency),
          })}
        </p>
      )}
    </section>
  );
}
