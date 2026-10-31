import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { DeadlineItem, Deadlines } from "../api/models";

const dayFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric" });
const monthFmt = new Intl.DateTimeFormat("en-GB", { month: "short" });

function parts(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  return { day: dayFmt.format(date), month: monthFmt.format(date) };
}

/** Plain-language timing, relative to today. */
function when(item: DeadlineItem): string {
  const d = item.days_until_due;
  if (d === null) return "No due date";
  if (d < 0) return `${-d} ${d === -1 ? "day" : "days"} late`;
  if (item.kind === "trip") return d === 0 ? "Leaves today" : d === 1 ? "Leaves tomorrow" : `Leaves in ${d} days`;
  if (d === 0) return "Due today";
  if (d === 1) return "Due tomorrow";
  return `In ${d} days`;
}

const GROUPS: { key: string; title: string; test: (d: number | null) => boolean }[] = [
  { key: "overdue", title: "Overdue", test: (d) => d !== null && d < 0 },
  { key: "soon", title: "Today and tomorrow", test: (d) => d !== null && d >= 0 && d <= 1 },
  { key: "week", title: "This week", test: (d) => d !== null && d >= 2 && d <= 7 },
  { key: "later", title: "Later", test: (d) => d === null || d > 7 },
];

const KIND_LABEL: Record<string, string> = { milestone: "Milestone", trip: "Trip" };

function Row({ item, showAssignee }: { item: DeadlineItem; showAssignee: boolean }) {
  const date = item.due_date ? parts(item.due_date) : null;
  const href =
    item.kind === "trip" ? `/app/projects/${item.project_id}/trips/${item.id}` : `/app/projects/${item.project_id}`;
  return (
    <li className={item.overdue ? "agenda__item agenda__item--late" : "agenda__item"}>
      <span className="agenda__date" aria-hidden={!date}>
        {date ? (
          <>
            <span className="agenda__day">{date.day}</span>
            <span className="agenda__month">{date.month}</span>
          </>
        ) : (
          <span className="agenda__month">—</span>
        )}
      </span>
      <span className="agenda__body">
        <Link to={href} className="agenda__title">
          {item.title}
        </Link>
        <span className="agenda__meta">
          <span className="agenda__when">{when(item)}</span>
          {KIND_LABEL[item.kind] && (
            <span className={`agenda__kind agenda__kind--${item.kind}`}>{KIND_LABEL[item.kind]}</span>
          )}
          <span>{item.project_name}</span>
          {showAssignee && item.kind === "task" && <span>{item.assignee ?? "Unassigned"}</span>}
        </span>
      </span>
    </li>
  );
}

/** What needs attention: overdue work and the next two weeks, or only the user's own open tasks. */
export function Agenda({ orgId, refreshKey }: { orgId: number; refreshKey: number }) {
  const [data, setData] = useState<Deadlines | null>(null);
  const [failed, setFailed] = useState(false);
  const [view, setView] = useState<"all" | "mine">("all");

  useEffect(() => {
    setFailed(false);
    api<Deadlines>(`/organizations/${orgId}/deadlines`)
      .then(setData)
      .catch(() => setFailed(true));
  }, [orgId, refreshKey]);

  const items = data ? (view === "all" ? data.items : data.my_tasks) : [];
  const hidden = data
    ? view === "all"
      ? data.item_count - data.items.length
      : data.my_task_count - data.my_tasks.length
    : 0;

  return (
    <section className="agenda" aria-labelledby="agenda-title">
      <div className="agenda__head">
        <h2 id="agenda-title">Agenda</h2>
        <div className="segmented" role="group" aria-label="Show">
          <button type="button" aria-pressed={view === "all"} onClick={() => setView("all")}>
            Everything
          </button>
          <button type="button" aria-pressed={view === "mine"} onClick={() => setView("mine")}>
            Mine{data && data.my_task_count > 0 ? ` (${data.my_task_count})` : ""}
          </button>
        </div>
      </div>

      {failed && <p className="muted">The agenda couldn't load. Reload the page to try again.</p>}
      {!data && !failed && <p className="muted">Loading…</p>}
      {data && items.length === 0 && (
        <p className="agenda__empty">
          {view === "all"
            ? `Nothing overdue or due in the next ${data.horizon_days} days.`
            : "No open tasks are assigned to you."}
        </p>
      )}

      {data &&
        GROUPS.map((g) => {
          const rows = items.filter((i) => g.test(i.days_until_due));
          if (!rows.length) return null;
          return (
            <div key={g.key} className={`agenda__group agenda__group--${g.key}`}>
              <h3>
                {g.title} <span className="agenda__count">{rows.length}</span>
              </h3>
              <ul>
                {rows.map((i) => (
                  <Row key={`${i.kind}-${i.id}`} item={i} showAssignee={view === "all"} />
                ))}
              </ul>
            </div>
          );
        })}
      {hidden > 0 && <p className="muted agenda__more">and {hidden} more.</p>}
    </section>
  );
}
