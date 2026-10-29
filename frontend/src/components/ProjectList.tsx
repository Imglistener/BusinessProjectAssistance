import type { Project } from "../api/models";
import { STATUS_LABEL, formatDateRange, formatMoney, formatPct } from "../lib/format";

function Budget({ project }: { project: Project }) {
  const hasBudget = Number(project.budget) > 0;
  if (!hasBudget && Number(project.actual) === 0) {
    return <p className="project__budget project__budget--none">No budget set</p>;
  }
  const used = project.consumed_pct === null ? 0 : Math.min(Number(project.consumed_pct), 100);
  return (
    <div className="project__budget">
      <p>
        <strong>{formatMoney(project.actual, project.currency)}</strong> spent of{" "}
        {formatMoney(project.budget, project.currency)}
      </p>
      <div
        className={project.over_budget ? "bar bar--over" : "bar"}
        role="progressbar"
        aria-label="Budget used"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(used)}
      >
        <div className="bar__fill" style={{ width: `${used}%` }} />
      </div>
      <p className={project.over_budget ? "project__note project__note--over" : "project__note"}>
        {project.over_budget
          ? `Over budget by ${formatMoney(project.variance, project.currency)}`
          : hasBudget
            ? `${formatPct(project.consumed_pct)} used, ${formatMoney(project.remaining, project.currency)} left`
            : null}
      </p>
    </div>
  );
}

export function ProjectList({ projects }: { projects: Project[] }) {
  return (
    <ul className="projects">
      {projects.map((p) => {
        const dates = formatDateRange(p.start_date, p.end_date);
        return (
          <li key={p.id} className="project">
            <div className="project__main">
              <h3 className="project__name">{p.name}</h3>
              <p className="project__meta">
                <span className={`status status--${p.status}`}>{STATUS_LABEL[p.status]}</span>
                {dates && <span>{dates}</span>}
                {p.overdue_task_count > 0 && (
                  <span className="project__overdue">
                    {p.overdue_task_count} overdue {p.overdue_task_count === 1 ? "task" : "tasks"}
                  </span>
                )}
              </p>
            </div>
            <Budget project={p} />
          </li>
        );
      })}
    </ul>
  );
}
