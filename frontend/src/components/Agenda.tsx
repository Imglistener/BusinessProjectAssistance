import { Flag, Plane } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { DeadlineItem, Deadlines } from "../api/models";
import { getLocale, t } from "../i18n";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";

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

function Row({ item, showAssignee }: { item: DeadlineItem; showAssignee: boolean }) {
  const date = item.due_date ? parts(item.due_date) : null;
  const href =
    item.kind === "trip" ? `/app/projects/${item.project_id}/trips/${item.id}` : `/app/projects/${item.project_id}`;
  return (
    <li>
      <Link
        to={href}
        className="group -mx-2 flex items-start gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-muted/60"
      >
        <span
          className={cn(
            "grid w-11 shrink-0 place-items-center rounded-lg border py-1 text-center leading-none",
            item.overdue ? "border-destructive/30 bg-destructive/5 text-destructive" : "bg-muted/40",
          )}
          aria-hidden={!date}
        >
          {date ? (
            <>
              <span className="tabular text-base font-semibold">{date.day}</span>
              <span className="mt-0.5 text-[10px] uppercase tracking-wide opacity-70">{date.month}</span>
            </>
          ) : (
            <span className="py-1.5 text-xs">—</span>
          )}
        </span>
        <span className="grid min-w-0 flex-1 gap-0.5">
          <span className="flex items-center gap-1.5 truncate text-sm font-medium">
            {item.kind === "milestone" && <Flag className="size-3.5 shrink-0 text-warning" aria-label={t("Milestone")} />}
            {item.kind === "trip" && <Plane className="size-3.5 shrink-0 text-primary" aria-label={t("Trip")} />}
            <span className="truncate">{item.title}</span>
          </span>
          <span className="flex flex-wrap gap-x-2 text-xs text-muted-foreground">
            <span className={cn(item.overdue && "font-medium text-destructive")}>{when(item)}</span>
            <span className="truncate">{item.project_name}</span>
            {showAssignee && item.kind === "task" && <span>{item.assignee ?? t("Unassigned")}</span>}
          </span>
        </span>
      </Link>
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
    <Card className="gap-4">
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle id="agenda-title" className="text-base">
          {t("Agenda")}
        </CardTitle>
        <ToggleGroup
          type="single"
          size="sm"
          variant="outline"
          value={view}
          onValueChange={(v) => v && setView(v as "all" | "mine")}
          aria-label={t("Show")}
        >
          <ToggleGroupItem value="all" className="px-3 text-xs">
            {t("Everything")}
          </ToggleGroupItem>
          <ToggleGroupItem value="mine" className="px-3 text-xs">
            {t("Mine")}
            {data && data.my_task_count > 0 ? ` (${data.my_task_count})` : ""}
          </ToggleGroupItem>
        </ToggleGroup>
      </CardHeader>
      <CardContent className="grid gap-5" aria-labelledby="agenda-title">
        {failed && <p className="text-sm text-muted-foreground">{t("The agenda couldn't load. Reload the page to try again.")}</p>}
        {!data && !failed && (
          <div className="grid gap-3">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="flex gap-3">
                <Skeleton className="h-11 w-11 rounded-lg" />
                <div className="grid flex-1 gap-2 py-1">
                  <Skeleton className="h-3.5 w-3/4" />
                  <Skeleton className="h-3 w-1/2" />
                </div>
              </div>
            ))}
          </div>
        )}
        {data && items.length === 0 && (
          <p className="rounded-lg border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
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
              <section key={g.key} className="grid gap-1">
                <h3
                  className={cn(
                    "flex items-center gap-2 text-xs font-medium text-muted-foreground",
                    g.key === "overdue" && "text-destructive",
                  )}
                >
                  {g.title}
                  <span className="tabular rounded-full bg-muted px-1.5 py-px text-[10px] text-muted-foreground">
                    {rows.length}
                  </span>
                </h3>
                <ul className="grid">
                  {rows.map((i) => (
                    <Row key={`${i.kind}-${i.id}`} item={i} showAssignee={view === "all"} />
                  ))}
                </ul>
              </section>
            );
          })}
        {hidden > 0 && <p className="text-xs text-muted-foreground">{t("and {count} more.", { count: hidden })}</p>}
      </CardContent>
    </Card>
  );
}
