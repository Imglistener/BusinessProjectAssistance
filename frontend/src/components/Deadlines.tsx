import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { DeadlineItem, Deadlines } from "../api/models";
import { formatDate } from "../lib/format";

function when(item: DeadlineItem): string {
  const d = item.days_until_due;
  if (d === null) return "No due date";
  if (d < 0) return `${-d} ${d === -1 ? "day" : "days"} overdue`;
  if (item.kind === "trip") return d === 0 ? "Leaves today" : d === 1 ? "Leaves tomorrow" : `Leaves in ${d} days`;
  if (d === 0) return "Due today";
  if (d === 1) return "Due tomorrow";
  return `Due in ${d} days`;
}

function Item({ item, showAssignee }: { item: DeadlineItem; showAssignee: boolean }) {
  return (
    <li className="deadline">
      <span className={item.overdue ? "deadline__when overdue" : "deadline__when"}>
        {when(item)}
        {item.due_date && <small>{formatDate(item.due_date)}</small>}
      </span>
      <span className="deadline__what">
        <span className="row__title">
          {item.title}
          {item.kind === "milestone" && <span className="tag">Milestone</span>}
          {item.kind === "trip" && <span className="tag">Trip</span>}
        </span>
        <span className="row__meta">
          <Link
            to={
              item.kind === "trip"
                ? `/app/projects/${item.project_id}/trips/${item.id}`
                : `/app/projects/${item.project_id}`
            }
          >
            {item.project_name}
          </Link>
          {showAssignee && item.kind === "task" && (item.assignee ? ` — ${item.assignee}` : " — Unassigned")}
        </span>
      </span>
    </li>
  );
}

/** Dashboard panels: overdue and upcoming work across projects, and the user's own open tasks. */
export function DeadlinesPanel({ orgId, refreshKey }: { orgId: number; refreshKey: number }) {
  const [data, setData] = useState<Deadlines | null>(null);

  useEffect(() => {
    api<Deadlines>(`/organizations/${orgId}/deadlines`)
      .then(setData)
      .catch(() => setData(null));
  }, [orgId, refreshKey]);

  if (!data || (data.items.length === 0 && data.my_tasks.length === 0)) return null;

  return (
    <div className="deadlines">
      {data.items.length > 0 && (
        <section className="panel" aria-labelledby="coming-up">
          <h2 id="coming-up" className="panel__title">
            Coming up
          </h2>
          <p className="muted deadlines__sub">Overdue and due in the next {data.horizon_days} days.</p>
          <ul className="deadlines__list">
            {data.items.map((i) => (
              <Item key={`${i.kind}-${i.id}`} item={i} showAssignee />
            ))}
          </ul>
          {data.item_count > data.items.length && (
            <p className="muted deadlines__more">and {data.item_count - data.items.length} more.</p>
          )}
        </section>
      )}
      {data.my_tasks.length > 0 && (
        <section className="panel" aria-labelledby="my-tasks">
          <h2 id="my-tasks" className="panel__title">
            My tasks
          </h2>
          <p className="muted deadlines__sub">Open tasks assigned to you.</p>
          <ul className="deadlines__list">
            {data.my_tasks.map((i) => (
              <Item key={`mine-${i.id}`} item={i} showAssignee={false} />
            ))}
          </ul>
          {data.my_task_count > data.my_tasks.length && (
            <p className="muted deadlines__more">and {data.my_task_count - data.my_tasks.length} more.</p>
          )}
        </section>
      )}
    </div>
  );
}
