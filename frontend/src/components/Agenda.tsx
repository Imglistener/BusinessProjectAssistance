import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { DeadlineItem, Deadlines } from "../api/models";
import { getLocale, t } from "../i18n";

const dayFmt = new Intl.DateTimeFormat(getLocale(), { day: "numeric" });
const monthFmt = new Intl.DateTimeFormat(getLocale(), { month: "short" });

function parts(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  return { day: dayFmt.format(date), month: monthFmt.format(date) };
}

/** Plain-language timing, relative to today. */
function when(item: DeadlineItem): string {
  const d = item.days_until_due;
  if (d === null) return t("No due date");
  if (d < 0) return t("{count} days late", { count: -d });
  if (item.kind === "trip") return d === 0 ? t("Leaves today") : d === 1 ? t("Leaves tomorrow") : t("Leaves in {count} days", { count: d });
  if (d === 0) return t("Due today");
  if (d === 1) return t("Due tomorrow");
  return t("In {count} days", { count: d });
}

const GROUPS: { key: string; title: string; test: (d: number | null) => boolean }[] = [
  { key: "overdue", title: t("Overdue"), test: (d) => d !== null && d < 0 },
  { key: "soon", title: t("Today and tomorrow"), test: (d) => d !== null && d >= 0 && d <= 1 },
  { key: "week", title: t("This week"), test: (d) => d !== null && d >= 2 && d <= 7 },
  { key: "later", title: t("Later"), test: (d) => d === null || d > 7 },
];

const KIND_LABEL: Record<string, string> = { milestone: t("Milestone"), trip: t("Trip") };

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
          {showAssignee && item.kind === "task" && <span>{item.assignee ?? t("Unassigned")}</span>}
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
        <h2 id="agenda-title">{t("Agenda")}</h2>
        <div className="segmented" role="group" aria-label={t("Show")}>
          <button type="button" aria-pressed={view === "all"} onClick={() => setView("all")}>
            {t("Everything")}
          </button>
          <button type="button" aria-pressed={view === "mine"} onClick={() => setView("mine")}>
            {t("Mine")}{data && data.my_task_count > 0 ? ` (${data.my_task_count})` : ""}
          </button>
        </div>
      </div>

      {failed && <p className="muted">{t("The agenda couldn't load. Reload the page to try again.")}</p>}
      {!data && !failed && <p className="muted">{t("Loading…")}</p>}
      {data && items.length === 0 && (
        <p className="agenda__empty">
          {view === "all"
            ? t("Nothing overdue or due in the next {horizon_days} days.", { horizon_days: data.horizon_days })
            : t("No open tasks are assigned to you.")}
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
      {hidden > 0 && <p className="muted agenda__more">{t("and {count} more.", { count: hidden })}</p>}
    </section>
  );
}
